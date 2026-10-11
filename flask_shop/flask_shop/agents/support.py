# -*- coding: utf-8 -*-
"""Persistent customer-service conversation helpers."""
from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Dict, Optional

from flask_shop import db, models


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


def ensure_conversation(
    tenant_id: int,
    session_id: str,
    *,
    customer_id: Optional[int] = None,
    intent: Optional[str] = None,
    subject: Optional[str] = None,
):
    row = get_conversation(tenant_id, session_id)
    if not row:
        row = models.SupportConversation(
            tenant_id=tenant_id,
            session_id=session_id,
            customer_id=customer_id,
            intent=intent,
            subject=(subject or "商城咨询")[:128],
            status="bot",
        )
        db.session.add(row)
        db.session.flush()
    else:
        if customer_id and not row.customer_id:
            row.customer_id = customer_id
        if intent:
            row.intent = intent[:64]
        if subject and (not row.subject or row.subject == "商城咨询"):
            row.subject = subject[:128]
        if row.status == "resolved":
            row.status = "bot"
            row.assignee_id = None
            row.need_human = 0
            row.resolved_at = None
            row.first_response_at = None
            row.satisfaction = None
            row.satisfaction_note = None
    return row


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


def persist_agent_turn(
    *,
    tenant_id: int,
    session_id: str,
    customer_id: Optional[int],
    user_text: str,
    result: Dict[str, Any],
):
    data = (result or {}).get("data") or {}
    intent = (data.get("intent") or {}).get("intent")
    conversation = ensure_conversation(
        tenant_id,
        session_id,
        customer_id=customer_id,
        intent=intent,
        subject=user_text[:128],
    )
    append_message(conversation, "customer", user_text, sender_id=customer_id)
    append_message(
        conversation,
        "ai",
        data.get("reply") or "",
        extra={
            "intent": intent,
            "agents_ran": data.get("agents_ran") or [],
            "need_human": bool(data.get("need_human")),
            "blocked": bool(data.get("blocked")),
            "citations": (data.get("citations") or [])[:3],
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
    save_memory_turn(
        tenant_id=tenant_id,
        session_id=session_id,
        customer_id=customer_id,
        user_text=user_text,
        reply=data.get("reply") or "",
        products=data.get("products") or [],
        intent=data.get("intent") or {},
    )
    return conversation


def persist_customer_waiting_message(conversation, content: str, customer_id: Optional[int]):
    append_message(conversation, "customer", content, sender_id=customer_id)
    db.session.commit()
    return conversation


def claim(conversation, staff_id: int):
    conversation.assignee_id = staff_id
    conversation.status = "active"
    conversation.need_human = 1
    append_message(conversation, "system", "客服已接入当前会话", sender_id=staff_id)
    db.session.commit()
    return conversation


def reply(conversation, staff_id: int, content: str):
    if conversation.status == "resolved":
        raise ValueError("会话已结束，请先重新打开")
    if conversation.assignee_id not in (None, staff_id):
        raise PermissionError("该会话已由其他客服接待")
    if conversation.assignee_id is None:
        conversation.assignee_id = staff_id
    conversation.status = "active"
    conversation.need_human = 1
    if not conversation.first_response_at:
        conversation.first_response_at = datetime.now()
    append_message(conversation, "staff", content, sender_id=staff_id)
    db.session.commit()
    return conversation


def resolve(conversation, staff_id: int):
    if conversation.assignee_id not in (None, staff_id):
        raise PermissionError("该会话已由其他客服接待")
    conversation.assignee_id = conversation.assignee_id or staff_id
    conversation.status = "resolved"
    conversation.need_human = 0
    conversation.resolved_at = datetime.now()
    append_message(conversation, "system", "本次人工服务已结束", sender_id=staff_id)
    db.session.commit()
    return conversation
