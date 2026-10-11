# -*- coding: utf-8 -*-
"""商家自动上架 Agent：仅 admin_ops 写库。"""
from __future__ import annotations

from .base import BaseAgent
from .listing import apply_listing, parse_listing_draft
from .types import AgentContext, AgentResult, AgentName


class ListingAgent(BaseAgent):
    name = AgentName.LISTING.value
    description = "解析上架指令并受控新建商品"

    def run(self, ctx: AgentContext) -> AgentResult:
        draft = parse_listing_draft(ctx.user_text or "")
        missing = draft.get("missing") or []
        actions = []
        listing = {"draft": draft, "applied": False, "product": None}

        if ctx.channel != "admin_ops":
            msg = "上架商品请店长在后台「运营助手」操作，顾客对话不能改商品库。"
            ctx.ops = {"listing": listing, "actions": [], "queues": {}}
            return AgentResult(ok=True, agent=self.name, message=msg, data=listing)

        if "name" in missing and "price" in missing:
            msg = "请说明要上架的商品名称和售价，例如：上架纯棉T恤，89元，库存30"
        elif "name" in missing:
            msg = "请补充商品名称，例如：上架纯棉T恤，89元，库存30"
        elif "price" in missing:
            msg = "请给出售价，例如：上架纯棉T恤，89元，库存30"
        else:
            msg = None

        if msg:
            ctx.ops = {"listing": listing, "actions": [], "queues": {}}
            return AgentResult(ok=True, agent=self.name, message=msg, data=listing)

        if not ctx.tenant_id:
            msg = "缺少店铺上下文，无法上架。"
            ctx.ops = {"listing": listing, "actions": [], "queues": {}}
            return AgentResult(ok=False, agent=self.name, message=msg, data=listing)

        result = apply_listing(
            ctx.tenant_id,
            draft,
            publish=True,
            enrich_with_llm=False,
        )
        listing.update(result)
        listing["applied"] = bool(result.get("ok"))
        listing["draft"] = draft

        if not result.get("ok"):
            ctx.ops = {"listing": listing, "actions": [], "queues": {}}
            return AgentResult(ok=False, agent=self.name, message=result.get("msg") or "上架失败", data=listing)

        p = result.get("product") or {}
        pid = result.get("product_id") or p.get("id")
        price = p.get("price")
        stock = p.get("number")
        lines = [
            f"已上架：{p.get('name')}  ¥{float(price or 0):.2f}  库存{int(stock or 0)}",
            f"商品ID {pid}。顾客端路径 /product/{pid}",
        ]
        if draft.get("stock_defaulted"):
            lines.append("未指定库存，已按 10 件上架，可在商品列表改数量。")
        lines.append("无主图时列表会显示待传主图，建议补实拍图。")

        actions = [
            {"type": "ops_queue", "label": "去商品列表", "path": "/product_list"},
            {"type": "ops_queue", "label": "继续添加商品", "path": "/add_product"},
        ]
        ctx.ops = {"listing": listing, "actions": actions, "queues": {}}
        return AgentResult(ok=True, agent=self.name, message="\n".join(lines), data=listing, handoff=None)
