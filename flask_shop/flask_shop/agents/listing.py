# -*- coding: utf-8 -*-
"""受控自动上架：只给商家后台用。缺品名/价格不写库。"""
from __future__ import annotations

import re
from typing import Any, Dict, Optional

from flask_shop import db, models
from flask_shop.utils.money import money_float
from flask_shop.utils.quota import check_product_quota
from flask_shop.utils.tenant_query import tenant_context

_PRICE = re.compile(r"(?:售价|价格|单价)?\s*(\d+(?:\.\d+)?)\s*(?:元|块钱?|块)")
_STOCK = re.compile(r"库存\s*[:：]?\s*(\d+)")
_PIECES = re.compile(r"(\d+)\s*件")
_PREFIX = re.compile(
    r"^(?:请|麻烦|帮我)?(?:把)?(?:商品)?"
    r"(?:上架|发布商品|新品上架|发布)\s*(?:一款|一个|一下)?"
    r"[:：,\s]*"
)
_OPS_PREFIX = re.compile(r"^运营分析[:：]\s*")


def parse_listing_draft(text: str) -> Dict[str, Any]:
    raw = _OPS_PREFIX.sub("", (text or "").strip())
    price = None
    pm = _PRICE.search(raw)
    if pm:
        try:
            price = float(pm.group(1))
        except (TypeError, ValueError):
            price = None

    stock = None
    sm = _STOCK.search(raw)
    if not sm:
        sm = _PIECES.search(raw)
    if sm:
        try:
            stock = int(sm.group(1))
        except (TypeError, ValueError):
            stock = None

    name_src = raw
    name_src = _PRICE.sub(" ", name_src)
    name_src = _STOCK.sub(" ", name_src)
    name_src = _PIECES.sub(" ", name_src)
    name_src = _PREFIX.sub("", name_src)
    name_src = re.sub(r"^(?:一款|一个|一下)\s*", "", name_src)
    name_src = re.sub(r"[\s,，。、；;]+", "", name_src).strip()
    name = name_src[:64] if name_src else None
    if name and len(name) < 2:
        name = None

    missing = []
    if not name:
        missing.append("name")
    if price is None or price <= 0:
        missing.append("price")

    return {
        "name": name,
        "price": price,
        "stock": stock,
        "stock_defaulted": stock is None,
        "missing": missing,
    }


def apply_listing(
    tenant_id: int,
    draft: Dict[str, Any],
    *,
    publish: bool = True,
    enrich_with_llm: bool = True,
) -> Dict[str, Any]:
    """新建商品。成功返回 ok=True 与 product dict。"""
    name = (draft.get("name") or "").strip()
    price = draft.get("price")
    if not name or price is None or float(price) <= 0:
        return {"ok": False, "msg": "上架需要品名和价格", "product": None}

    ok_q, err_q = check_product_quota(tenant_id)
    if not ok_q:
        return {"ok": False, "msg": err_q, "product": None}

    stock = draft.get("stock")
    if stock is None:
        stock = 10
    stock = max(int(stock), 0)

    content = {}
    try:
        from flask_shop.agents.content_agent import run_product_content_agent
        cr = run_product_content_agent(
            tenant_id,
            {"name": name, "price": price, "number": stock},
            use_llm=enrich_with_llm,
        )
        content = (cr or {}).get("data") or {}
    except Exception:
        content = {}

    title = str(content.get("title") or name).strip()[:128] or name[:128]
    intro = str(content.get("sell_points") or content.get("description") or "").strip()[:2000]

    with tenant_context(disabled=True):
        product = models.Product(
            tenant_id=tenant_id,
            name=title,
            price=money_float(price),
            number=stock,
            introduce=intro or None,
            state=2 if publish else 0,
        )
        if hasattr(product, "sell_points") and content.get("sell_points"):
            product.sell_points = str(content.get("sell_points"))[:2000]
        db.session.add(product)
        db.session.commit()
        pdata = product.to_dict()
        pid = product.id

    return {
        "ok": True,
        "msg": "已生成并上架" if publish else "已保存未上架",
        "published": bool(publish),
        "product_id": pid,
        "product": pdata,
        "content": content,
        "stock_defaulted": bool(draft.get("stock_defaulted")),
    }
