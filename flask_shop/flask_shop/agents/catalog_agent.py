# -*- coding: utf-8 -*-
"""选品检索 Agent：对接商品库过滤排序。"""
from __future__ import annotations

from .base import BaseAgent
from .types import AgentContext, AgentResult, AgentName
from .tools import shop_tools
from . import knowledge as knowledge_lib


class CatalogAgent(BaseAgent):
    name = AgentName.CATALOG.value
    description = "商品检索/推荐/对比"

    def _from_knowledge(self, ctx: AgentContext, query: str):
        """商品库没命中时用数据中心知识卡兜底，只取已上架商品。"""
        if not query:
            return []
        try:
            cards = knowledge_lib.load_knowledge(ctx.tenant_id, query, limit=5)
        except Exception:
            return []
        out = []
        for c in cards:
            pid = c.get("product_id")
            if not pid:
                continue
            try:
                price = float(c.get("price") or 0)
                stock = int(c.get("stock") or 0)
            except (TypeError, ValueError):
                continue
            out.append({
                "id": pid,
                "name": c.get("title"),
                "price": price,
                "stock": stock,
                "in_stock": stock > 0,
            })
        return out

    def run(self, ctx: AgentContext) -> AgentResult:
        intent = ctx.intent or {}
        kws = intent.get("keywords") or []
        budget = intent.get("budget_max")
        primary = intent.get("intent") or "search"

        # 检索词：有关键词用关键词，否则热门
        query = kws[0] if kws else ""
        items = shop_tools.search_products(
            keyword=query,
            tenant_slug=ctx.tenant_slug,
            tenant_id=ctx.tenant_id,
            max_price=budget,
            limit=8,
        )
        # 无结果则先查数据中心知识卡，再退回热门，避免答非所问
        fallback_used = False
        if not items and query:
            fallback_used = True
            items = self._from_knowledge(ctx, query) or shop_tools.search_products(
                keyword="",
                tenant_slug=ctx.tenant_slug,
                tenant_id=ctx.tenant_id,
                max_price=budget,
                limit=6,
            )

        in_stock = [x for x in items if x.get("in_stock")]
        ranked = sorted(
            in_stock or items,
            key=lambda x: (not x.get("in_stock"), x.get("price") or 0),
        )


        compare = []
        if primary == "compare" and len(ranked) >= 2:
            a, b = ranked[0], ranked[1]
            compare = [
                {"id": a["id"], "name": a["name"], "price": a["price"], "stock": a["stock"]},
                {"id": b["id"], "name": b["name"], "price": b["price"], "stock": b["stock"]},
            ]

        ctx.catalog = {
            "query": query,
            "budget_max": budget,
            "items": ranked,
            "compare": compare,
            "count": len(ranked),
            "fallback_used": fallback_used if "fallback_used" in dir() else False,
        }

        if not ranked:
            qshow = query or "该条件"
            msg = f"本店暂无符合「{qshow}」的在售商品。"
            if budget is not None:
                msg += f"（预算 ≤¥{budget:.0f}）"
            msg += " 可换关键词，或到首页浏览全部商品。"
            return AgentResult(ok=True, agent=self.name, message=msg, data=ctx.catalog, handoff="promo")

        prefix = "未精确命中，为你推荐店内其它在售" if (ctx.catalog or {}).get("fallback_used") else "为你找到"
        lines = [f"{prefix} {len(ranked)} 件商品" + (f"（预算 ≤¥{budget:.0f}）" if budget else "") + "："]
        for i, p in enumerate(ranked[:5], 1):
            stock = "有货" if p["in_stock"] else "缺货"
            lines.append(f"{i}. {p['name']}  ¥{p['price']:.2f}  库存{p['stock']}（{stock}）")
        if compare:
            lines.append(
                f"对比：{compare[0]['name']}(¥{compare[0]['price']}) vs {compare[1]['name']}(¥{compare[1]['price']})"
            )
        lines.append("可以说「买第1个」或到商品页下单。")

        return AgentResult(
            ok=True,
            agent=self.name,
            message="\n".join(lines),
            data=ctx.catalog,
            handoff="promo",
        )
