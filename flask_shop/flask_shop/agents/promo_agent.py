# -*- coding: utf-8 -*-
"""优惠凑单 Agent：读取 t_coupons + 组合建议。"""
from __future__ import annotations

from .base import BaseAgent
from .types import AgentContext, AgentResult, AgentName
from .tools import shop_tools


class PromoAgent(BaseAgent):
    name = AgentName.PROMO.value
    description = "满减/凑单/组合建议"

    FALLBACK_RULES = [
        {"id": "ship_free_99", "name": "满99包邮", "threshold": 99, "amount_off": 0, "coupon_type": "shipping_free"},
        {"id": "save_20_199", "name": "满199减20", "threshold": 199, "amount_off": 20, "coupon_type": "amount_off"},
    ]

    def run(self, ctx: AgentContext) -> AgentResult:
        items = (ctx.catalog or {}).get("items") or []
        coupons = shop_tools.list_coupons(ctx.tenant_slug, ctx.tenant_id) or []
        rules = coupons if coupons else self.FALLBACK_RULES

        if not items:
            ctx.promo = {"applicable": [], "tips": ["先选品后再算优惠"], "coupons": rules}
            return AgentResult(ok=True, agent=self.name, message="暂无商品可算优惠。", data=ctx.promo, handoff="risk")

        top = items[0]
        price = float(top.get("price") or 0)
        tips, applicable = [], []
        for r in rules:
            th = float(r.get("threshold") or 0)
            name = r.get("name") or "优惠"
            off = float(r.get("amount_off") or 0)
            ctype = r.get("coupon_type") or r.get("type") or ""
            if price >= th and th > 0:
                applicable.append({**r, "status": "已满足", "on_item": top.get("name")})
            elif th > 0:
                gap = th - price
                tips.append(f"再买 ¥{gap:.2f} 可享受「{name}」")
                applicable.append({**r, "status": "未满足", "gap": round(gap, 2)})
            elif off > 0:
                applicable.append({**r, "status": "可用", "on_item": top.get("name")})

        combo = None
        if len(items) >= 2:
            a, b = items[0], items[1]
            combo = {
                "items": [a["id"], b["id"]],
                "names": [a["name"], b["name"]],
                "sum": round(float(a["price"]) + float(b["price"]), 2),
                "note": "组合购买更容易满包邮门槛",
            }

        draft = shop_tools.create_draft_order_hint(top)
        ctx.promo = {
            "focus_product": top,
            "applicable": applicable,
            "tips": tips,
            "combo": combo,
            "coupons": rules,
            "draft_order_hint": draft,
            "payment_hint": "个人微信收款码转账，备注订单号，店长确认后发货",
        }

        lines = ["优惠与凑单建议："]
        if any(x.get("status") == "已满足" for x in applicable):
            lines.append("· 当前首选商品已满足部分优惠门槛。")
        for t in tips[:3]:
            lines.append(f"· {t}")
        if combo:
            lines.append(f"· 组合：{combo['names'][0]} + {combo['names'][1]} ≈ ¥{combo['sum']}")
        lines.append(f"· 想买「{top.get('name')}」可说「就买第1个」或打开商品页下单。")
        lines.append("· 付款：微信扫码，备注订单号。")

        return AgentResult(ok=True, agent=self.name, message="\n".join(lines), data=ctx.promo, handoff="risk")
