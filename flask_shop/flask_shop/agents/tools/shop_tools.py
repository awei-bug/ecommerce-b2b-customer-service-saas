# -*- coding: utf-8 -*-
"""对接真实商品库 / 订单库的只读工具（Agent 不直连乱七八糟的 SQL）。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import case

from flask_shop import models
from flask_shop.utils.money import money_float
from flask_shop.utils.tenant_query import tenant_context


def _tenant_id(slug: str = "demo", tenant_id: Optional[int] = None) -> Optional[int]:
    if tenant_id:
        return tenant_id
    with tenant_context(disabled=True):
        t = models.Tenant.query.filter_by(slug=slug, status=1).first()
        return t.id if t else None


def search_products(
    keyword: str = "",
    tenant_slug: str = "demo",
    tenant_id: Optional[int] = None,
    max_price: Optional[float] = None,
    min_price: Optional[float] = None,
    limit: int = 8,
) -> List[Dict[str, Any]]:
    tid = _tenant_id(tenant_slug, tenant_id)
    if not tid:
        return []
    with tenant_context(disabled=True):
        q = models.Product.query.filter_by(tenant_id=tid)
        # 上架：state 2 或 null
        q = q.filter((models.Product.state == 2) | (models.Product.state.is_(None)))
        kw = (keyword or "").strip()
        if kw:
            like = f"%{kw}%"
            q = q.filter(
                (models.Product.name.like(like)) | (models.Product.introduce.like(like))
            )
        if min_price is not None:
            q = q.filter(models.Product.price >= float(min_price))
        if max_price is not None:
            q = q.filter(models.Product.price <= float(max_price))
        if kw:
            # 相关度优先：品名命中 > 简介命中 > 其余，避免新品(hot_number=0)永远沉底
            relevance = case(
                (models.Product.name.like(like), 2),
                (models.Product.introduce.like(like), 1),
                else_=0,
            )
            rows = q.order_by(
                relevance.desc(), models.Product.hot_number.desc(), models.Product.id.desc()
            ).limit(limit).all()
        else:
            rows = q.order_by(
                models.Product.hot_number.desc(), models.Product.id.desc()
            ).limit(limit).all()
        out = []
        for p in rows:
            stock = int(p.stock_total())
            out.append({
                "id": p.id,
                "name": p.name,
                "price": money_float(p.price),
                "stock": stock,
                "introduce": (p.introduce or "")[:120],
                "big_img": p.big_img,
                "in_stock": stock > 0,
            })
        return out


def get_product(pid: int, tenant_slug: str = "demo", tenant_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
    tid = _tenant_id(tenant_slug, tenant_id)
    if not tid:
        return None
    with tenant_context(disabled=True):
        p = models.Product.query.filter_by(id=pid, tenant_id=tid).first()
        if not p:
            return None
        stock = int(p.stock_total())
        return {
            "id": p.id,
            "name": p.name,
            "price": money_float(p.price),
            "stock": stock,
            "introduce": p.introduce or "",
            "big_img": p.big_img,
            "in_stock": stock > 0,
        }


def list_orders(
    tenant_slug: str = "demo",
    tenant_id: Optional[int] = None,
    customer_id: Optional[int] = None,
    status: Optional[str] = None,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    tid = _tenant_id(tenant_slug, tenant_id)
    if not tid:
        return []
    with tenant_context(disabled=True):
        q = models.Order.query.filter_by(tenant_id=tid)
        if customer_id:
            q = q.filter_by(customer_id=customer_id)
        if status:
            q = q.filter_by(status=status)
        rows = q.order_by(models.Order.id.desc()).limit(limit).all()
        return [
            {
                "id": o.id,
                "order_no": o.order_no,
                "status": o.status,
                "price": float(o.price or 0),
                "address": o.address,
                "customer_id": o.customer_id,
            }
            for o in rows
        ]


def list_low_stock(
    tenant_slug: str = "demo",
    tenant_id: Optional[int] = None,
    threshold: int = 5,
    limit: int = 5,
) -> List[Dict[str, Any]]:
    tid = _tenant_id(tenant_slug, tenant_id)
    if not tid:
        return []
    with tenant_context(disabled=True):
        rows = (
            models.Product.query.filter(
                models.Product.tenant_id == tid,
                models.Product.number <= int(threshold),
            )
            .order_by(models.Product.number.asc(), models.Product.id.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "id": p.id,
                "name": p.name,
                "stock": int(p.number or 0),
                "price": money_float(p.price),
                "path": "/product_list",
            }
            for p in rows
        ]


def order_stats(tenant_slug: str = "demo", tenant_id: Optional[int] = None) -> Dict[str, Any]:
    tid = _tenant_id(tenant_slug, tenant_id)
    if not tid:
        return {}
    with tenant_context(disabled=True):
        total = models.Order.query.filter_by(tenant_id=tid).count()
        pending = models.Order.query.filter_by(tenant_id=tid, status="pending_pay").count()
        paid = models.Order.query.filter_by(tenant_id=tid, status="paid").count()
        shipped = models.Order.query.filter_by(tenant_id=tid, status="shipped").count()
        products = models.Product.query.filter_by(tenant_id=tid).count()
        low_stock = models.Product.query.filter(
            models.Product.tenant_id == tid,
            models.Product.number <= 5,
        ).count()
        return {
            "orders_total": total,
            "pending_pay": pending,
            "paid_waiting_ship": paid,
            "shipped": shipped,
            "products": products,
            "low_stock": low_stock,
        }


def shop_profile(tenant_slug: str = "demo") -> Dict[str, Any]:
    with tenant_context(disabled=True):
        t = models.Tenant.query.filter_by(slug=tenant_slug).first()
        if not t:
            return {}
        return {
            "id": t.id,
            "name": t.name,
            "slug": t.slug,
            "pay_guide": (t.pay_guide or "")[:200],
            "has_wechat_qr": bool(getattr(t, "pay_qr_wechat", None)),
            "contact_phone": t.contact_phone,
            "payment_mode": "manual_qr",
        }


def list_coupons(tenant_slug: str = "demo", tenant_id=None):
    tid = _tenant_id(tenant_slug, tenant_id)
    if not tid:
        return []
    with tenant_context(disabled=True):
        if not hasattr(models, "Coupon"):
            return []
        rows = (
            models.Coupon.query.filter_by(tenant_id=tid, status=1)
            .order_by(models.Coupon.threshold.asc())
            .all()
        )
        return [c.to_dict() for c in rows]


def create_draft_order_hint(product: dict) -> dict:
    """仅返回受控建单所需信息，不写库。path 带 buy=1，前端可直接打开确认弹窗。"""
    if not product:
        return {}
    pid = product.get("id")
    in_stock = product.get("in_stock")
    if in_stock is None:
        in_stock = int(product.get("stock") or 0) > 0
    return {
        "action": "buy",
        "product_id": pid,
        "name": product.get("name"),
        "price": product.get("price"),
        "in_stock": bool(in_stock),
        "path": f"/product/{pid}?buy=1",
        "note": "点立即购买打开下单确认；未登录会先去登录。Agent 不改库存/收款状态。",
    }
