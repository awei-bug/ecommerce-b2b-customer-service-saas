# -*- coding: utf-8 -*-
"""订单物流 Agent：查单、付款指引、物流摘要（只读+引导，下单仍走正式 API）。"""
from __future__ import annotations

from .base import BaseAgent
from .types import AgentContext, AgentResult, AgentName
from .tools import shop_tools
import re


class OrderAgent(BaseAgent):
    name = AgentName.ORDER.value
    description = "订单/物流/付款指引"

    def run(self, ctx: AgentContext) -> AgentResult:
        intent = (ctx.intent or {}).get("intent")
        profile = shop_tools.shop_profile(ctx.tenant_slug)
        orders = []
        if ctx.customer_id:
            orders = shop_tools.list_orders(
                tenant_slug=ctx.tenant_slug,
                tenant_id=ctx.tenant_id,
                customer_id=ctx.customer_id,
                limit=5,
            )
        else:
            orders = []

        ctx.order = {
            "orders": orders,
            "shop": profile,
            "can_place_order": True,
            "place_order_path": "/product/:id?buy=1 → 确认弹窗 → 扫码支付",
            "actions": [],
            "login_required": False,
        }

        if intent == "pay_help":
            msg = (
                "付款方式：\n"
                "1. 选好商品后点「立即购买」下单\n"
                "2. 微信扫描店铺收款码\n"
                "3. 备注填写订单号\n"
                "4. 店长确认到账后发货\n"
            )
            if profile.get("has_wechat_qr"):
                msg += "（已配置微信收款码）"
            else:
                msg += "（店主尚未上传收款码，请联系客服）"
            phone = profile.get("contact_phone")
            if phone:
                ctx.order["actions"].append({
                    "type": "human",
                    "label": f"联系店长 {phone}",
                    "path": f"tel:{phone}",
                })
            return AgentResult(ok=True, agent=self.name, message=msg, data=ctx.order, handoff="cs")

        if intent in ("order_status", "track", "refund"):
            if not ctx.customer_id:
                ctx.order["login_required"] = True
                ctx.order["actions"].append({
                    "type": "login",
                    "label": "去登录查订单",
                    "path": "/login?redirect=/orders",
                })
                return AgentResult(
                    ok=True,
                    agent=self.name,
                    message="查询订单需要先登录。点下面按钮登录后即可查看。",
                    data=ctx.order,
                    handoff="cs",
                )
            if not orders:
                return AgentResult(
                    ok=True,
                    agent=self.name,
                    message="暂无订单记录。可以说「有什么货」，我帮你挑一件。",
                    data=ctx.order,
                    handoff="catalog",
                )
            lines = ["你的最近订单："]
            for o in orders:
                lines.append(
                    f"· {o['order_no']}  ¥{o['price']:.2f}  状态 {o['status']}"
                )
            ctx.order["actions"].append({
                "type": "orders",
                "label": "打开我的订单",
                "path": "/orders",
            })
            if intent == "track":
                lines.append("物流详情可在「我的订单 → 详情」查看；发货后会显示物流信息。")
            if intent == "refund":
                lines.append("售后请说明订单号与原因，需要的话我帮你转店长。")
            return AgentResult(ok=True, agent=self.name, message="\n".join(lines), data=ctx.order, handoff="cs")

        top = ((ctx.catalog or {}).get("items") or [None])[0]
        m = re.search(r"id=(\d+)", ctx.user_text or "")
        if m:
            p = shop_tools.get_product(int(m.group(1)), ctx.tenant_slug, ctx.tenant_id)
            if p:
                top = p
        draft = shop_tools.create_draft_order_hint(top) if top else {}
        ctx.order["draft_order_hint"] = draft
        if draft.get("path") and draft.get("in_stock", True):
            ctx.order["actions"].append({
                "type": "buy",
                "label": f"立即购买 {draft.get('name') or ''}".strip(),
                "path": draft["path"],
                "product_id": draft.get("product_id"),
                "name": draft.get("name"),
                "price": draft.get("price"),
            })
        if top:
            msg = (
                f"推荐「{top['name']}」¥{float(top['price']):.2f}。\n"
                "点「立即购买」即可打开确认下单；未登录会先去登录。\n"
                "Agent 不会直接改库存或标记已付款。"
            )
        else:
            msg = "下单路径：选商品 → 立即购买 → 支付页扫码 → 店长确认收款。"
        return AgentResult(ok=True, agent=self.name, message=msg, data=ctx.order, handoff="cs")
