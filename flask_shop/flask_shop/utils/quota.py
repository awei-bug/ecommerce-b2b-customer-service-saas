# -*- coding: utf-8 -*-
"""多租户套餐配额（P3-5 骨架）。"""
from __future__ import annotations

from flask import current_app

from flask_shop import models
from flask_shop.utils.tenant_query import tenant_context

# plan_code -> limits
PLAN_LIMITS = {
    "free": {"max_products": 50, "max_staff": 3, "max_orders_day": 200},
    "pro": {"max_products": 5000, "max_staff": 50, "max_orders_day": 50000},
    "enterprise": {"max_products": 100000, "max_staff": 500, "max_orders_day": 1000000},
}


def get_limits(plan_code: str | None) -> dict:
    code = (plan_code or "free").lower()
    return dict(PLAN_LIMITS.get(code) or PLAN_LIMITS["free"])


def check_product_quota(tenant_id: int) -> tuple[bool, str]:
    with tenant_context(disabled=True):
        t = models.Tenant.query.get(tenant_id)
        if not t:
            return False, "租户不存在"
        lim = get_limits(getattr(t, "plan_code", None))
        n = models.Product.query.filter_by(tenant_id=tenant_id).count()
        if n >= lim["max_products"]:
            return False, f"已达套餐商品上限 {lim['max_products']}（plan={t.plan_code or 'free'}）"
        return True, ""
