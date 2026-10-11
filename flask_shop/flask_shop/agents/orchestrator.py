# -*- coding: utf-8 -*-
"""编排器：按意图调度多个专用 Agent，汇总回复。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .types import AgentContext
from .intent_agent import IntentAgent
from .catalog_agent import CatalogAgent
from .promo_agent import PromoAgent
from .order_agent import OrderAgent
from .cs_agent import CustomerServiceAgent
from .ops_agent import OpsAgent
from .listing_agent import ListingAgent
from .risk_agent import RiskAgent
from .grounding import ground_reply
from . import knowledge as knowledge_lib


class AgentOrchestrator:
    """
    协作策略：
    1) Intent
    2) Catalog/Order/Ops 分支
    3) Promo（选品路径）
    4) Risk
    5) CS（可用 LLM 润色）
    """

    def __init__(self):
        self.intent = IntentAgent()
        self.catalog = CatalogAgent()
        self.promo = PromoAgent()
        self.order = OrderAgent()
        self.cs = CustomerServiceAgent()
        self.ops = OpsAgent()
        self.listing = ListingAgent()
        self.risk = RiskAgent()

    def run_chat(
        self,
        user_text: str,
        *,
        tenant_slug: str = "demo",
        tenant_id: Optional[int] = None,
        customer_id: Optional[int] = None,
        staff_id: Optional[int] = None,
        channel: str = "mall_chat",
        memory: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        ctx = AgentContext(
            tenant_slug=tenant_slug or "demo",
            tenant_id=tenant_id,
            customer_id=customer_id,
            staff_id=staff_id,
            channel=channel,
            user_text=user_text or "",
            memory=memory or {},
        )

        results: List[Dict[str, Any]] = []

        r_intent = self.intent.safe_run(ctx)
        results.append(r_intent.to_dict())
        intent_name = (ctx.intent or {}).get("intent") or "greeting"

        if intent_name in ("search", "recommend", "compare"):
            results.append(self.catalog.safe_run(ctx).to_dict())
            # 仅在用户明确询问优惠/包邮/凑单时加载促销，普通导购不必等待无关查询。
            if any(word in (user_text or '') for word in ("优惠", "满减", "包邮", "凑单", "优惠券")):
                results.append(self.promo.safe_run(ctx).to_dict())
            r_risk = self.risk.safe_run(ctx)
            results.append(r_risk.to_dict())
            if not r_risk.ok:
                return self._pack(ctx, results, user_message=r_risk.message, blocked=True)
            # 只有明确购买/下单时才加载订单与收款上下文。
            if any(word in (user_text or '') for word in ("买", "下单", "付款", "支付")):
                results.append(self.order.safe_run(ctx).to_dict())
        elif intent_name in ("order_status", "track", "pay_help", "refund"):
            results.append(self.order.safe_run(ctx).to_dict())
            results.append(self.risk.safe_run(ctx).to_dict())
        elif intent_name == "ops":
            results.append(self.ops.safe_run(ctx).to_dict())
            results.append(self.risk.safe_run(ctx).to_dict())
        elif intent_name == "list_product":
            results.append(self.listing.safe_run(ctx).to_dict())
            results.append(self.risk.safe_run(ctx).to_dict())
        else:
            results.append(self.risk.safe_run(ctx).to_dict())

        # Ops and listing already produce complete, structured merchant-facing
        # replies. Sending them through CS adds no value and makes core admin
        # actions depend on an external LLM.
        r_cs = None
        if not (channel == "admin_ops" and intent_name in ("ops", "list_product")):
            r_cs = self.cs.safe_run(ctx)
            results.append(r_cs.to_dict())

        user_message = self._compose_user_message(ctx, results, r_cs.message if r_cs else "")
        products_preview = ((ctx.catalog or {}).get("items") or [])[:5]
        knowledge_cards = (ctx.knowledge or {}).get("cards") or []
        user_message, gmeta = ground_reply(user_message, products_preview, knowledge_cards)
        ctx.add_trace("grounding", "apply", gmeta)
        return self._pack(
            ctx,
            results,
            user_message=user_message,
            blocked=bool((ctx.risk or {}).get("blocked")),
            need_human=bool((ctx.cs or {}).get("need_human")),
        )

    def _compose_user_message(self, ctx: AgentContext, results: List[Dict], cs_msg: str) -> str:
        if (ctx.intent or {}).get("blocked_listing"):
            return "上架商品请店长在后台「运营助手」操作，顾客对话不能改商品库。"
        for r in results:
            if r.get("agent") == "listing" and r.get("message"):
                return r["message"]
        if (ctx.cs or {}).get("llm", {}).get("used") and cs_msg:
            return cs_msg
        if (ctx.cs or {}).get("grounded_query") and cs_msg:
            return cs_msg

        prefer = {"catalog", "promo", "order", "ops", "listing"}
        chunks = []
        for r in results:
            if r.get("agent") in prefer and r.get("message"):
                chunks.append(r["message"])
        if not chunks:
            return cs_msg
        body = "\n\n".join(chunks[:2])
        if (ctx.cs or {}).get("need_human"):
            body += "\n\n" + cs_msg
        elif cs_msg and (ctx.intent or {}).get("intent") in ("greeting", "cs"):
            body = cs_msg
        return body

    def _merge_actions(self, ctx: AgentContext, products: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        merged: List[Dict[str, Any]] = []
        seen = set()

        def add(act):
            if not isinstance(act, dict):
                return
            path = str(act.get("path") or "").strip()
            if not path or path in seen:
                return
            seen.add(path)
            merged.append(act)

        for src in (ctx.order, ctx.ops, ctx.cs):
            if isinstance(src, dict):
                for a in src.get("actions") or []:
                    add(a)

        for p in products or []:
            if not p:
                continue
            in_stock = p.get("in_stock")
            if in_stock is None:
                in_stock = int(p.get("stock") or 0) > 0
            if not in_stock:
                continue
            pid = p.get("id")
            if not pid:
                continue
            add({
                "type": "buy",
                "label": f"立即购买 {p.get('name') or ''}".strip(),
                "path": f"/product/{pid}?buy=1",
                "product_id": pid,
                "name": p.get("name"),
                "price": p.get("price"),
            })
        return merged[:8]

    def _pack(self, ctx, results, user_message, blocked=False, need_human=False):
        products = ((ctx.catalog or {}).get("items") or [])[:5]
        cards = (ctx.knowledge or {}).get("cards") or []
        citations = knowledge_lib.citations(cards)
        default_suggests = ["有什么货", "怎么付钱", "我的单到哪了", "转店长"]
        return {
            "status": 200,
            "msg": "ok",
            "data": {
                "session_id": ctx.session_id,
                "reply": user_message,
                "intent": ctx.intent,
                "knowledge": {
                    "loaded": bool((ctx.knowledge or {}).get("loaded")),
                    "count": len(cards),
                    "source": (ctx.knowledge or {}).get("source"),
                },
                "citations": citations,
                "products": products,
                "promo": ctx.promo,
                "orders": (ctx.order or {}).get("orders") or [],
                "ops": ctx.ops,
                "risk": ctx.risk,
                "need_human": need_human,
                "blocked": blocked,
                "agents_ran": [r.get("agent") for r in results],
                "trace": ctx.trace[-20:],
                "suggested_replies": (ctx.cs or {}).get("suggested_replies") or default_suggests,
                "draft_order_hint": (ctx.order or {}).get("draft_order_hint")
                or (ctx.promo or {}).get("draft_order_hint"),
                "actions": self._merge_actions(ctx, products),
                "login_required": bool((ctx.order or {}).get("login_required")),
                "memory": {
                    "turn_count": int((ctx.memory or {}).get("turn_count") or 0),
                    "preferences": (ctx.memory or {}).get("preferences") or {},
                    "updated_at": (ctx.memory or {}).get("updated_at"),
                },
            },
        }


orchestrator = AgentOrchestrator()
