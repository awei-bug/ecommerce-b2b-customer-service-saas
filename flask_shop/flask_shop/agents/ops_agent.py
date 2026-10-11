# -*- coding: utf-8 -*-
"""运营分析 Agent：对内统计与建议。"""
from __future__ import annotations

from .base import BaseAgent
from .types import AgentContext, AgentResult, AgentName
from .tools import shop_tools


def _queue_item(order: dict, status: str) -> dict:
    return {
        "id": order.get("id"),
        "order_no": order.get("order_no"),
        "price": order.get("price"),
        "status": order.get("status") or status,
        "path": f"/order_list?status={status}&order_no={order.get('order_no') or ''}",
    }


class OpsAgent(BaseAgent):
    name = AgentName.OPS.value
    description = "经营数据与运营建议"

    def run(self, ctx: AgentContext) -> AgentResult:
        stats = shop_tools.order_stats(ctx.tenant_slug, ctx.tenant_id)
        profile = shop_tools.shop_profile(ctx.tenant_slug)
        pending_pay = shop_tools.list_orders(
            ctx.tenant_slug, ctx.tenant_id, status="pending_pay", limit=5
        )
        pending_ship = shop_tools.list_orders(
            ctx.tenant_slug, ctx.tenant_id, status="paid", limit=5
        )
        low_items = shop_tools.list_low_stock(ctx.tenant_slug, ctx.tenant_id, limit=5)

        tips = []
        if stats.get("pending_pay", 0) > 0:
            tips.append(f"有 {stats['pending_pay']} 笔待确认收款，建议尽快核账。")
        if stats.get("paid_waiting_ship", 0) > 0:
            tips.append(f"有 {stats['paid_waiting_ship']} 笔已付款待发货，优先履约。")
        if stats.get("low_stock", 0) > 0:
            tips.append(f"{stats['low_stock']} 个 SKU 库存≤5，注意补货。")
        if not profile.get("has_wechat_qr"):
            tips.append("尚未配置微信收款码，顾客付款路径不完整。")
        if not tips:
            tips.append("主链路平稳：保持商品上新与及时确认收款即可。")

        queues = {
            "pending_pay": [_queue_item(o, "pending_pay") for o in pending_pay],
            "pending_ship": [_queue_item(o, "paid") for o in pending_ship],
            "low_stock": low_items,
        }
        actions = []
        if ctx.channel == "admin_ops":
            n_pay = int(stats.get("pending_pay") or 0)
            n_ship = int(stats.get("paid_waiting_ship") or 0)
            if n_pay:
                actions.append({
                    "type": "ops_queue",
                    "label": f"去确认收款（{n_pay}）",
                    "path": "/order_list?status=pending_pay",
                })
            if n_ship:
                actions.append({
                    "type": "ops_queue",
                    "label": f"去发货（{n_ship}）",
                    "path": "/order_list?status=paid",
                })
            if not profile.get("has_wechat_qr"):
                actions.append({
                    "type": "ops_queue",
                    "label": "去配置收款码",
                    "path": "/shop_settings",
                })
            if stats.get("low_stock", 0):
                actions.append({
                    "type": "ops_queue",
                    "label": f"去看低库存（{stats.get('low_stock')}）",
                    "path": "/product_list",
                })

        ctx.ops = {
            "stats": stats,
            "tips": tips,
            "shop": profile,
            "queues": queues,
            "actions": actions,
        }
        lines = ["运营速览："]
        lines.append(
            f"订单总数 {stats.get('orders_total', 0)}｜待付款 {stats.get('pending_pay', 0)}｜"
            f"待发货 {stats.get('paid_waiting_ship', 0)}｜已发货 {stats.get('shipped', 0)}"
        )
        lines.append(f"在售商品 {stats.get('products', 0)}｜低库存 {stats.get('low_stock', 0)}")
        lines.append("建议：")
        for t in tips:
            lines.append(f"· {t}")
        if ctx.channel == "admin_ops":
            lines.append("点下方按钮直接处理，不必只看数字。")
        return AgentResult(ok=True, agent=self.name, message="\n".join(lines), data=ctx.ops, handoff=None)
