# -*- coding: utf-8 -*-
"""把商城自建商品登记到数据中心，建立 external_id 绑定。

方向与 hub_sync 相反。此前只有「数据中心 → 商城」的单向通道，商城自建商品
在数据中心没有身份，导致下游（内容平台、跨境）无法引用它，库存事件也只能
带一个空的 external_id。本模块补上另一半：商品上行。

两条硬约束：
1. external_id 必须稳定且可反解，重复上行不得产生第二个身份；
2. 上行成功的同时必须在 t_product_knowledge 建绑定。只推不绑，下一次
   hub 同步会把它当成「同名商品」判为冲突，或重复新建一条商品。
"""
from __future__ import annotations

from typing import Any, Dict

from flask import current_app

from flask_shop import db, models
from flask_shop.utils import hub_client
from flask_shop.utils.money import money_float
from flask_shop.utils.tenant_query import tenant_context
from flask_shop.utils.hub_sync import _upsert_knowledge


class PublishError(RuntimeError):
    """上行失败，携带可直接回给前端的消息。"""


def build_external_id(tenant_id: int, product_id: int) -> str:
    """商城侧商品的稳定标识。格式固定，便于从事件里反查来源。"""
    return f"yg-{int(tenant_id)}-{int(product_id)}"


def _split_points(raw: str) -> list[str]:
    text = str(raw or "").strip()
    if not text:
        return []
    for sep in ("；", ";", "|"):
        text = text.replace(sep, "\n")
    return [line.strip() for line in text.splitlines() if line.strip()][:10]


def _images(product) -> list[str]:
    urls = []
    for candidate in (getattr(product, "big_img", ""), getattr(product, "small_img", "")):
        url = str(candidate or "").strip()
        if url and url not in urls:
            urls.append(url[:255])
    return urls


def build_item(product, external_id: str) -> Dict[str, Any]:
    return {
        "external_id": external_id,
        "title": str(product.name or "")[:128],
        "price": money_float(product.price),
        "stock": int(product.number or 0),
        "desc_zh": str(product.introduce or "")[:4000] or None,
        "selling_points": _split_points(product.sell_points),
        "images": _images(product),
        "source_job_id": f"shop:{product.id}",
    }


def _existing_binding(tenant_id: int, product_id: int):
    with tenant_context(tenant_id=tenant_id):
        return (models.ProductKnowledge.query
                .filter_by(tenant_id=tenant_id, product_id=product_id)
                .order_by(models.ProductKnowledge.id.desc())
                .first())


def publish_product(tenant, product_id: int) -> Dict[str, Any]:
    """上行单个商品并建立绑定，返回 external_id 与数据中心动作。"""
    tenant_id = int(getattr(tenant, "id"))
    with tenant_context(tenant_id=tenant_id):
        product = models.Product.query.filter_by(id=int(product_id), tenant_id=tenant_id).first()
    if product is None:
        raise PublishError("商品不存在或不属于当前店铺")

    binding = _existing_binding(tenant_id, product.id)
    external_id = (binding.external_id if binding else "") or build_external_id(tenant_id, product.id)
    item = build_item(product, external_id)

    response = hub_client.ingest([item], source="shop_publish", job_id=f"shop:{product.id}")
    results = response.get("results") or []
    first = results[0] if results else {}
    if not first.get("ok"):
        raise PublishError(first.get("message") or "数据中心拒绝了该商品")

    # 以数据中心回读的记录为准写本地知识副本：版本号与 content_hash
    # 必须与枢纽一致，否则下一轮同步会被判成「内容已变化」。
    record = hub_client.fetch_product(external_id) or item
    status = "published" if int(product.state or 0) == 2 else "draft"
    with tenant_context(tenant_id=tenant_id):
        knowledge = (models.ProductKnowledge.query
                     .filter_by(tenant_id=tenant_id, external_id=external_id)
                     .with_for_update()
                     .first())
        _upsert_knowledge(tenant_id, record, knowledge, product.id, status)
        db.session.commit()

    current_app.logger.info(
        "hub publish product=%s external_id=%s action=%s", product.id, external_id, first.get("action")
    )
    return {
        "product_id": product.id,
        "external_id": external_id,
        "action": first.get("action"),
        "version": first.get("version"),
        "status": status,
        "reused_binding": bool(binding),
    }
