# -*- coding: utf-8 -*-
"""Persistent customer-service conversation helpers."""
from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import func, or_, update
from sqlalchemy.exc import IntegrityError
from flask import current_app

from flask_shop import db, models
from flask_shop.utils.money import money_float


OPEN_STATUSES = ("bot", "waiting", "active")


def get_conversation(tenant_id: int, session_id: str):
    return models.SupportConversation.query.filter_by(
        tenant_id=tenant_id,
        session_id=session_id,
    ).first()


def _scope_key(customer_id: Optional[int], session_id: str) -> str:
    return f"customer:{int(customer_id)}" if customer_id else f"session:{str(session_id)[:96]}"


def get_memory_context(tenant_id: int, session_id: str, customer_id: Optional[int] = None) -> Dict[str, Any]:
    """读取持久化记忆；已登录顾客跨会话复用，匿名顾客按会话复用。"""
    if not tenant_id or not session_id:
        return {}
    row = models.AgentMemory.query.filter_by(
        tenant_id=tenant_id,
        scope_key=_scope_key(customer_id, session_id),
    ).first()
    return row.to_context() if row else {}


def _extract_preferences(user_text: str, intent: Dict[str, Any], products: list) -> Dict[str, Any]:
    text = str(user_text or '')
    preferences: Dict[str, Any] = {}
    if intent.get('budget_max') is not None:
        preferences['budget_max'] = intent.get('budget_max')
    keywords = [str(x).strip() for x in (intent.get('keywords') or []) if str(x).strip()]
    if keywords:
        preferences['keywords'] = keywords[:6]
    size = re.search(r'(?:尺码|码数|大小)\s*[:：]?\s*([SMLX]{1,4}|均码|加大码)', text, re.I)
    if not size:
        # Customers commonly write the size inline, e.g. "黑色L码夹克".
        size = re.search(r'(?<![A-Za-z])([SMLX]{1,4})\s*码', text, re.I)
    if size:
        preferences['size'] = size.group(1).upper()
    colors = re.findall(r'(黑色|白色|灰色|蓝色|绿色|红色|卡其|米色|棕色|藏青)', text)
    if colors:
        preferences['colors'] = list(dict.fromkeys(colors))[:5]
    if products:
        preferences['last_product_names'] = [str(p.get('name')) for p in products[:5] if p.get('name')]
    return preferences


def save_memory_turn(
    *, tenant_id: int, session_id: str, customer_id: Optional[int], user_text: str,
    reply: str, products: Optional[list] = None, intent: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """把最近对话与可解释偏好写入数据库，不调用模型。"""
    scope_key = _scope_key(customer_id, session_id)
    row = models.AgentMemory.query.filter_by(tenant_id=tenant_id, scope_key=scope_key).first()
    if not row:
        row = models.AgentMemory(tenant_id=tenant_id, customer_id=customer_id, scope_key=scope_key)
        db.session.add(row)
    elif customer_id and not row.customer_id:
        row.customer_id = customer_id
    old = row.to_context() if row.id else {}
    turns = list(old.get('recent_turns') or [])
    turns.extend([
        {'role': 'user', 'text': str(user_text or '')[:500]},
        {'role': 'assistant', 'text': str(reply or '')[:1000]},
    ])
    turns = turns[-16:]
    current_products = list(products or old.get('last_products') or [])[:5]
    current_intent = dict(intent or old.get('last_intent') or {})
    preferences = dict(old.get('preferences') or {})
    preferences.update(_extract_preferences(user_text, current_intent, current_products))
    row.summary = '；'.join(
        f"{item.get('role')}: {item.get('text')}" for item in turns[-6:] if item.get('text')
    )[:4000]
    row.preferences_json = json.dumps(preferences, ensure_ascii=False)
    row.recent_turns_json = json.dumps(turns, ensure_ascii=False)
    row.last_products_json = json.dumps(current_products, ensure_ascii=False)
    row.last_intent_json = json.dumps(current_intent, ensure_ascii=False)
    row.turn_count = int(row.turn_count or 0) + 1
    db.session.commit()
    return row.to_context()


def _get_or_create_conversation(tenant_id, session_id, customer_id, subject):
    row = get_conversation(tenant_id, session_id)
    if not row:
        row = models.SupportConversation(
            tenant_id=tenant_id,
            session_id=session_id,
            customer_id=customer_id,
            subject=(subject or "商城咨询")[:128],
            status="bot",
        )
        db.session.add(row)
        try:
            db.session.flush()
        except IntegrityError:
            db.session.rollback()
            row = get_conversation(tenant_id, session_id)
            if not row:
                raise
    return row


def _lock_conversation(conversation, customer_id):
    model = models.SupportConversation
    db.session.execute(
        update(model).where(model.id == conversation.id, model.tenant_id == conversation.tenant_id)
        .values(status=model.status, update_time=model.update_time)
        .execution_options(synchronize_session=False)
    )
    db.session.refresh(conversation)
    if conversation.customer_id and conversation.customer_id != customer_id:
        raise PermissionError("无权访问该会话")
    if customer_id and not conversation.customer_id:
        conversation.customer_id = customer_id
    return conversation


def append_message(
    conversation,
    sender_type: str,
    content: str,
    *,
    sender_id: Optional[int] = None,
    extra: Optional[Dict[str, Any]] = None,
):
    value = str(content or "").strip()
    if not value:
        return None
    message = models.SupportMessage(
        tenant_id=conversation.tenant_id,
        conversation_id=conversation.id,
        sender_type=sender_type,
        sender_id=sender_id,
        content=value[:8000],
        extra_json=json.dumps(extra or {}, ensure_ascii=False) if extra else None,
    )
    db.session.add(message)
    conversation.last_message = value[:500]
    conversation.message_count = int(conversation.message_count or 0) + 1
    return message


def _product_id(value):
    if isinstance(value, bool):
        return None
    text = str(value or "")
    if not text.isascii() or not text.isdigit() or len(text) > 10:
        return None
    number = int(text)
    return number if 0 < number <= 2147483647 else None


def refresh_product_slots(tenant_id, *product_lists):
    slots = [items[:5] if isinstance(items, list) else [] for items in product_lists]
    ids = {
        product_id for items in slots for item in items
        if isinstance(item, dict) and (product_id := _product_id(item.get('id')))
    }
    products = {}
    if ids:
        rows = models.Product.query.filter(
            models.Product.tenant_id == tenant_id,
            models.Product.id.in_(ids),
            or_(models.Product.state == 2, models.Product.state.is_(None)),
        ).populate_existing().all()
        stocks = dict(db.session.query(models.ProductSku.product_id, func.sum(models.ProductSku.stock)).filter(
            models.ProductSku.tenant_id == tenant_id,
            models.ProductSku.product_id.in_(ids),
            models.ProductSku.status == 1,
        ).group_by(models.ProductSku.product_id).all())
        for product in rows:
            stock = int(stocks.get(product.id) or 0) if product.id in stocks else int(product.number or 0)
            products[product.id] = {
                'id': product.id, 'name': product.name, 'price': money_float(product.price),
                'stock': stock, 'in_stock': stock > 0,
            }
    return [[products.get(_product_id(item.get('id'))) if isinstance(item, dict) else None
             for item in items] for items in slots]


def _replay_metadata(data):
    products = data.get("products") if isinstance(data.get("products"), list) else []
    product_ids = []
    for product in products[:5]:
        product_id = _product_id(product.get("id")) if isinstance(product, dict) else None
        if product_id and product_id not in product_ids:
            product_ids.append(product_id)
    draft = data.get("draft_order_hint")
    draft_id = _product_id(draft.get("product_id")) if isinstance(draft, dict) else None
    actions = data.get("actions") if isinstance(data.get("actions"), list) else []
    safe_actions = []
    for action in actions[:8]:
        if not isinstance(action, dict):
            continue
        kind = action.get("type")
        path = action.get("path")
        if (kind, path) in (("login", "/login?redirect=/orders"), ("orders", "/orders")) and kind not in safe_actions:
            safe_actions.append(kind)
        elif kind == "human" and isinstance(path, str) and path.startswith("tel:") and kind not in safe_actions:
            safe_actions.append(kind)
    return {
        "product_ids": product_ids,
        "draft_product_id": draft_id,
        "safe_actions": safe_actions,
        "login_required": bool(data.get("login_required")),
    }


def customer_history_messages(tenant_id, customer_id, messages, contact_phone=None):
    items = [message.to_dict() for message in messages]
    product_ids = set()
    for item in items:
        extra = item.get("extra")
        if item.get("sender_type") != "ai" or not isinstance(extra, dict) or "product_ids" not in extra:
            continue
        ids = extra.get("product_ids") if isinstance(extra.get("product_ids"), list) else []
        product_ids.update(product_id for value in ids[:5] if (product_id := _product_id(value)))
        draft_id = _product_id(extra.get("draft_product_id"))
        if draft_id:
            product_ids.add(draft_id)

    products = {}
    if product_ids:
        rows = models.Product.query.filter(
            models.Product.tenant_id == tenant_id,
            models.Product.id.in_(product_ids),
            or_(models.Product.state == 2, models.Product.state.is_(None)),
        ).all()
        stocks = dict(db.session.query(models.ProductSku.product_id, func.sum(models.ProductSku.stock)).filter(
            models.ProductSku.tenant_id == tenant_id,
            models.ProductSku.product_id.in_(product_ids),
            models.ProductSku.status == 1,
        ).group_by(models.ProductSku.product_id).all())
        for product in rows:
            stock = int(stocks.get(product.id) or 0) if product.id in stocks else int(product.number or 0)
            products[product.id] = {
                "id": product.id,
                "name": product.name,
                "price": money_float(product.price),
                "stock": stock,
                "in_stock": stock > 0,
            }

    for item in items:
        extra = item.get("extra")
        if item.get("sender_type") != "ai" or not isinstance(extra, dict) or "product_ids" not in extra:
            continue
        ids = extra.get("product_ids") if isinstance(extra.get("product_ids"), list) else []
        extra["products"] = [products[product_id] for value in ids[:5]
                             if (product_id := _product_id(value)) in products]
        draft = products.get(_product_id(extra.get("draft_product_id")))
        extra["draft_order_hint"] = ({
            "name": draft["name"], "path": f"/product/{draft['id']}?buy=1",
        } if draft and draft["in_stock"] else None)
        types = extra.get("safe_actions") if isinstance(extra.get("safe_actions"), list) else []
        extra["actions"] = []
        if "login" in types and not customer_id:
            extra["actions"].append({"type": "login", "label": "去登录查订单", "path": "/login?redirect=/orders"})
        if "orders" in types and customer_id:
            extra["actions"].append({"type": "orders", "label": "打开我的订单", "path": "/orders"})
        if "human" in types and contact_phone and re.fullmatch(r"\+?[0-9][0-9 -]{2,30}", contact_phone):
            extra["actions"].append({"type": "human", "label": f"联系店长 {contact_phone}", "path": f"tel:{contact_phone}"})
        extra["login_required"] = bool(extra.get("login_required")) and not customer_id
        for field in ("product_ids", "draft_product_id", "safe_actions"):
            extra.pop(field, None)
    return items


def persist_agent_turn(
    *,
    tenant_id: int,
    session_id: str,
    customer_id: Optional[int],
    user_text: str,
    result: Dict[str, Any],
    initial_status: Optional[str] = None,
    initial_resolved_at: Optional[datetime] = None,
):
    data = (result or {}).get("data") or {}
    intent = (data.get("intent") or {}).get("intent")
    conversation = _get_or_create_conversation(tenant_id, session_id, customer_id, user_text)
    _lock_conversation(conversation, customer_id)
    if conversation.status in ("waiting", "active") or (
        conversation.status == "resolved" and
        (initial_status != "resolved" or conversation.resolved_at != initial_resolved_at)
    ):
        customer_message = append_message(conversation, "customer", user_text, sender_id=customer_id)
        db.session.commit()
        return conversation, False, customer_message.id, None
    if conversation.status == "resolved":
        conversation.status = "bot"
        conversation.assignee_id = None
        conversation.need_human = 0
        conversation.resolved_at = None
        conversation.first_response_at = None
        conversation.satisfaction = None
        conversation.satisfaction_note = None
    if intent:
        conversation.intent = intent[:64]
    if user_text and (not conversation.subject or conversation.subject == "商城咨询"):
        conversation.subject = user_text[:128]
    customer_message = append_message(conversation, "customer", user_text, sender_id=customer_id)
    ai_message = append_message(
        conversation,
        "ai",
        data.get("reply") or "",
        extra={
            "intent": intent,
            "agents_ran": data.get("agents_ran") or [],
            "need_human": bool(data.get("need_human")),
            "blocked": bool(data.get("blocked")),
            "citations": (data.get("citations") or [])[:3],
            **_replay_metadata(data),
        },
    )
    if data.get("need_human") or data.get("blocked"):
        conversation.status = "waiting"
        conversation.need_human = 1
        if data.get("blocked"):
            conversation.priority = "urgent"
        elif intent == "refund" and conversation.priority == "normal":
            conversation.priority = "high"
    db.session.commit()
    try:
        save_memory_turn(
            tenant_id=tenant_id,
            session_id=session_id,
            customer_id=customer_id,
            user_text=user_text,
            reply=data.get("reply") or "",
            products=data.get("products") or [],
            intent=data.get("intent") or {},
        )
    except Exception:
        db.session.rollback()
        current_app.logger.exception("导购记忆保存失败")
    return conversation, True, customer_message.id, ai_message.id if ai_message else None


def persist_customer_waiting_message(conversation, content: str, customer_id: Optional[int]):
    _lock_conversation(conversation, customer_id)
    if conversation.status not in ("waiting", "active"):
        db.session.rollback()
        return None
    message = append_message(conversation, "customer", content, sender_id=customer_id)
    db.session.commit()
    return conversation, message.id


def claim(conversation, staff_id: int):
    updated = _transition(conversation, staff_id, "claim")
    if not updated:
        return conversation
    append_message(conversation, "system", "客服已接入当前会话", sender_id=staff_id)
    db.session.commit()
    return conversation


def reply(conversation, staff_id: int, content: str):
    _transition(conversation, staff_id, "reply")
    append_message(conversation, "staff", content, sender_id=staff_id)
    db.session.commit()
    return conversation


def resolve(conversation, staff_id: int):
    _transition(conversation, staff_id, "resolve")
    append_message(conversation, "system", "本次人工服务已结束", sender_id=staff_id)
    db.session.commit()
    return conversation


def _transition(conversation, staff_id: int, action: str):
    model = models.SupportConversation
    conditions = [
        model.id == conversation.id,
        model.tenant_id == conversation.tenant_id,
        model.status != "resolved",
        or_(model.assignee_id.is_(None), model.assignee_id == staff_id),
    ]
    values = {"assignee_id": staff_id, "status": "active", "need_human": 1}
    if action == "claim":
        conditions.append(or_(model.status != "active", model.assignee_id.is_(None)))
    elif action == "reply":
        values["first_response_at"] = db.func.coalesce(model.first_response_at, datetime.now())
    elif action == "resolve":
        values.update(status="resolved", need_human=0, resolved_at=datetime.now())
    else:
        raise ValueError("不支持的会话操作")

    result = db.session.execute(
        update(model).where(*conditions).values(**values).execution_options(synchronize_session=False)
    )
    if not result.rowcount:
        db.session.rollback()
        db.session.refresh(conversation)
        if conversation.status == "resolved":
            raise ValueError("会话已结束，请先重新打开")
        if conversation.assignee_id not in (None, staff_id):
            raise PermissionError("该会话已由其他客服接待")
        if action == "claim" and conversation.status == "active" and conversation.assignee_id == staff_id:
            return False
        raise ValueError("会话状态已变化，请刷新后重试")
    db.session.refresh(conversation)
    return True
