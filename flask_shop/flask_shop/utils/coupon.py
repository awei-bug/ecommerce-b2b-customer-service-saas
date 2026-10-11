# -*- coding: utf-8 -*-
"""满减 / 包邮券计算（金额一律走 Decimal 分位）。"""
from __future__ import annotations

from flask_shop.utils.money import money_float, to_money


def coupon_effect(coupon, goods_amount, freight_amount):
    """
    返回 dict: eligible, discount, freight, save, reason
    discount 计入应付减免；shipping_free 时 freight 变为 0，discount 为减免的运费。
    """
    goods = to_money(goods_amount)
    freight = to_money(freight_amount)
    empty = {
        "eligible": False,
        "discount": 0.0,
        "freight": money_float(freight),
        "save": 0.0,
        "reason": None,
    }
    if not coupon or int(getattr(coupon, "status", 0) or 0) != 1:
        return empty
    th = to_money(coupon.threshold)
    if goods < th:
        empty["reason"] = "未满门槛"
        return empty
    ctype = (coupon.coupon_type or "amount_off")
    if ctype == "shipping_free":
        if freight <= 0:
            empty["reason"] = "运费已免"
            return empty
        return {
            "eligible": True,
            "discount": money_float(freight),
            "freight": 0.0,
            "save": money_float(freight),
            "reason": coupon.name,
        }
    off = to_money(coupon.amount_off)
    if off <= 0:
        return empty
    if off > goods:
        off = goods
    return {
        "eligible": True,
        "discount": money_float(off),
        "freight": money_float(freight),
        "save": money_float(off),
        "reason": coupon.name,
    }


def pick_best_coupon(coupons, goods_amount, freight_amount):
    best = None
    best_save = to_money(0)
    for c in coupons or []:
        eff = coupon_effect(c, goods_amount, freight_amount)
        if not eff["eligible"]:
            continue
        save = to_money(eff["save"])
        if save > best_save:
            best_save = save
            best = c
    return best


def list_active_coupons(tenant_id):
    from flask_shop import models
    if not tenant_id or not hasattr(models, "Coupon"):
        return []
    return (
        models.Coupon.query.filter_by(tenant_id=tenant_id, status=1)
        .order_by(models.Coupon.threshold.asc())
        .all()
    )