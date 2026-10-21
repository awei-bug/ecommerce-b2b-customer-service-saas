# -*- coding: utf-8 -*-
"""从数据中心同步商品到电商库，并回执上架结果。

设计原则
- 数据中心是权威，本函数只做「消费」，不回写内容
- 缺价格的记录不建商品，保留为待补价，避免发明价格
- 同步幂等：同一 external_id 重复同步只更新不新建
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from flask import current_app

from flask_shop import db, models
from flask_shop.utils import hub_client
from flask_shop.utils.money import money_float
from flask_shop.utils.quota import check_product_quota
from flask_shop.utils.tenant_query import tenant_context

DEFAULT_STOCK = 10


def _knowledge_payload(item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "external_id": item.get("external_id"),
        "title": item.get("title"),
        "subtitle": item.get("subtitle"),
        "title_en": item.get("title_en"),
        "price": item.get("price"),
        "currency": item.get("currency") or "CNY",
        "stock": item.get("stock"),
        "category": item.get("category"),
        "brand": item.get("brand"),
        "scenario": item.get("scenario"),
        "tags": item.get("tags") or [],
        "selling_points": item.get("selling_points") or [],
        "spec": item.get("spec") or {},
        "faq": item.get("faq") or [],
        "desc_zh": item.get("desc_zh"),
        "images": item.get("images") or [],
        "video_url": item.get("video_url"),
        "source_job_id": item.get("source_job_id"),
        "version": item.get("version"),
    }


def _first_image(item: Dict[str, Any]) -> str:
    images = item.get("images") or []
    for url in images:
        url = str(url or "").strip()
        if url:
            return url[:255]
    return ""


def _find_knowledge(tenant_id: int, external_id: str):
    with tenant_context(tenant_id=tenant_id):
        return models.ProductKnowledge.query.filter_by(external_id=external_id).first()


def _get_product(tenant_id: int, product_id: Optional[int]):
    if not product_id:
        return None
    with tenant_context(tenant_id=tenant_id):
        return db.session.get(models.Product, int(product_id))


def _apply_item(tenant_id: int, item: Dict[str, Any], publish: bool) -> Dict[str, Any]:
    external_id = str(item.get("external_id") or "").strip()
    if not external_id:
        return {"external_id": None, "action": "error", "message": "缺少 external_id"}

    name = str(item.get("title") or "").strip()
    if not name:
        return {"external_id": external_id, "action": "error", "message": "缺少商品名称"}

    price = item.get("price")
    try:
        price_val = float(price) if price is not None else 0.0
    except (TypeError, ValueError):
        price_val = 0.0

    knowledge = _find_knowledge(tenant_id, external_id)
    product = _get_product(tenant_id, knowledge.product_id if knowledge else None)

    if price_val <= 0:
        # 不发明价格：只登记知识，等人工补价后再同步
        _upsert_knowledge(tenant_id, item, knowledge, None, "pending_price")
        return {
            "external_id": external_id,
            "action": "pending",
            "name": name,
            "message": "缺少售价，已登记待补价",
        }

    linked_before = bool(knowledge and knowledge.product_id)
    if product is None:
        with tenant_context(tenant_id=tenant_id):
            exists = models.Product.query.filter_by(name=name).first()
        if exists:
            product = exists
        else:
            ok, msg = check_product_quota(tenant_id)
            if not ok:
                return {"external_id": external_id, "action": "error", "name": name, "message": msg}
            product = models.Product(
                tenant_id=tenant_id,
                name=name[:128],
                price=price_val,
                number=int(item.get("stock") or DEFAULT_STOCK),
                state=2 if publish else 0,
            )
            db.session.add(product)
            db.session.flush()

    product.name = name[:128]
    product.price = price_val
    if item.get("stock") is not None:
        try:
            product.number = int(item.get("stock"))
        except (TypeError, ValueError):
            pass
    if publish:
        product.state = 2

    scenario = str(item.get("scenario") or "").strip()
    points = item.get("selling_points") or []
    desc = str(item.get("desc_zh") or "").strip()
    introduce = desc
    if not introduce and points:
        introduce = "；".join(str(p) for p in points[:5])
    if scenario and scenario not in (introduce or ""):
        introduce = f"{introduce} 适用场景：{scenario}".strip()
    product.introduce = (introduce or "")[:2000] or None
    product.sell_points = ("；".join(str(p) for p in points[:10]) or "")[:2000] or None
    cover = _first_image(item)
    if cover:
        product.big_img = cover
        product.small_img = cover

    _upsert_knowledge(tenant_id, item, knowledge, product.id, "published" if publish else "draft")

    return {
        "external_id": external_id,
        "action": "updated" if linked_before else "created",
        "product_id": product.id,
        "name": name,
        "price": money_float(price_val),
    }


def _upsert_knowledge(tenant_id, item, knowledge, product_id, status):
    payload = _knowledge_payload(item)
    raw = json.dumps(payload, ensure_ascii=False)
    now = datetime.now()
    if knowledge is None:
        knowledge = models.ProductKnowledge(
            tenant_id=tenant_id,
            external_id=str(item.get("external_id")),
            product_id=product_id,
            title=str(item.get("title") or "")[:128],
            price=item.get("price") or 0,
            category=str(item.get("category") or "")[:64] or None,
            knowledge_json=raw,
            content_hash=item.get("content_hash"),
            version=int(item.get("version") or 1),
            status=status,
            synced_at=now,
        )
        db.session.add(knowledge)
        return knowledge
    knowledge.product_id = product_id or knowledge.product_id
    knowledge.title = str(item.get("title") or "")[:128]
    knowledge.price = item.get("price") or 0
    knowledge.category = str(item.get("category") or "")[:64] or None
    knowledge.knowledge_json = raw
    knowledge.content_hash = item.get("content_hash")
    knowledge.version = int(item.get("version") or 1)
    knowledge.status = status
    knowledge.synced_at = now
    return knowledge


def sync_from_hub(
    tenant,
    status: str = "",
    since: str = "",
    limit: int = 50,
    publish: bool = True,
    ack: bool = True,
) -> Dict[str, Any]:
    """拉取数据中心记录并落库。

    :param tenant: Tenant 实例
    :param status: 限定状态；留空取全部非 archived
    :param since: ISO 时间串，增量同步起点
    :param publish: True 上架，False 存草稿
    """
    items = hub_client.fetch_products(status=status, since=since, limit=limit)
    result: Dict[str, Any] = {
        "tenant_id": getattr(tenant, "id", None),
        "tenant_slug": getattr(tenant, "slug", None),
        "received": len(items),
        "created": [],
        "updated": [],
        "pending": [],
        "errors": [],
        "ack_errors": [],
    }

    for item in items:
        try:
            with tenant_context(tenant_id=getattr(tenant, "id", None)):
                row = _apply_item(tenant.id, item, publish)
            db.session.commit()
        except Exception as exc:  # 单条失败不影响整批
            db.session.rollback()
            current_app.logger.exception("hub sync failed for %s", item.get("external_id"))
            row = {
                "external_id": item.get("external_id"),
                "action": "error",
                "message": str(exc),
            }

        bucket = {
            "created": "created",
            "updated": "updated",
            "pending": "pending",
            "error": "errors",
        }.get(str(row.get("action")), "errors")
        result[bucket].append(row)

        if ack and row.get("action") in ("created", "updated") and row.get("product_id"):
            try:
                hub_client.ack(row["external_id"], row["product_id"], "published" if publish else "draft")
            except Exception as exc:
                result["ack_errors"].append({"external_id": row.get("external_id"), "message": str(exc)})

    result["summary"] = {
        "created": len(result["created"]),
        "updated": len(result["updated"]),
        "pending": len(result["pending"]),
        "errors": len(result["errors"]),
        "ack_errors": len(result["ack_errors"]),
    }
    return result
