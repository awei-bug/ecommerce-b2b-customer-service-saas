# -*- coding: utf-8 -*-
"""客服对话 Agent：规则兜底 + OpenRouter 润色/生成。"""
from __future__ import annotations

import json
import re

from .base import BaseAgent
from .types import AgentContext, AgentResult, AgentName
from .tools.llm_client import llm_enabled, chat_completions
from .tools import shop_tools
from . import knowledge as knowledge_lib


class CustomerServiceAgent(BaseAgent):
    name = AgentName.CS.value
    description = "客服应答与人工移交判断"

    HUMAN_TRIGGERS = [r"人工", r"投诉", r"报警", r"律师", r"12315", r"打假", r"欺诈", r"转店长"]
    SUGGESTS = ["有什么货", "怎么付钱", "我的单到哪了", "转店长"]

    # 思维链泄漏：部分模型会把推理过程当正文返回，直接丢弃改用规则回复
    THINK_LEAKS = [
        r"here'?s a thinking process",
        r"thinking process",
        r"let me think",
        r"<think>",
        r"</think>",
        r"as an ai",
        r"^thinking[:：]",
        r"思考过程[:：]",
        r"^\s*\d+\.\s*\*\*(分析|analyze)",
    ]

    def _leaked_reasoning(self, text: str) -> bool:
        if not text:
            return True
        return any(re.search(p, text, re.I | re.M) for p in self.THINK_LEAKS)

    def run(self, ctx: AgentContext) -> AgentResult:
        text = ctx.user_text or ""
        intent = (ctx.intent or {}).get("intent")
        need_human = any(re.search(p, text, re.I) for p in self.HUMAN_TRIGGERS)
        if intent == "refund":
            need_human = True

        # 先加载商家确认过的店铺事实与商品知识，再决定是否允许 AI 作答。
        if not (ctx.knowledge or {}).get("loaded"):
            try:
                cards = knowledge_lib.load_knowledge(ctx.tenant_id, text, limit=3)
                ctx.knowledge = {
                    "loaded": True,
                    "cards": cards,
                    "count": len(cards),
                    "source": "hub" if cards and cards[0].get("external_id") else "local",
                }
            except Exception:
                ctx.knowledge = {"loaded": True, "cards": [], "count": 0, "source": "error"}

        cards = (ctx.knowledge or {}).get("cards") or []
        grounded_query = knowledge_lib.requires_grounded_answer(text, intent)
        knowledge_miss = grounded_query and not cards
        if knowledge_miss:
            need_human = True

        rule_reply = self._rule_reply(ctx, intent, need_human, knowledge_miss, grounded_query)
        final_reply = rule_reply
        llm_meta = {"used": False}

        if (
            ctx.channel != "admin_ops"
            and llm_enabled()
            and not knowledge_miss
            and not (ctx.risk or {}).get("blocked")
            and self._should_polish(ctx, need_human)
        ):
            polished = self._llm_reply(ctx, rule_reply, need_human)
            content = (polished or {}).get("content") or ""
            if polished and content and not self._leaked_reasoning(content):
                final_reply = content
                llm_meta = {"used": True, "model": polished.get("model")}
            elif polished:
                llm_meta = {"used": False, "model": polished.get("model"), "action": "dropped_leak"}

        actions = []
        if need_human:
            phone = ((ctx.order or {}).get("shop") or {}).get("contact_phone")
            if not phone:
                phone = shop_tools.shop_profile(ctx.tenant_slug).get("contact_phone")
            if phone:
                actions.append({
                    "type": "human",
                    "label": f"联系店长 {phone}",
                    "path": f"tel:{phone}",
                })

        ctx.cs = {
            "reply": final_reply,
            "need_human": bool(need_human),
            "reason": "knowledge_miss" if knowledge_miss else ("trigger_keywords" if need_human else "bot_ok"),
            "grounded_query": bool(grounded_query),
            "suggested_replies": list(self.SUGGESTS),
            "llm": llm_meta,
            "rule_reply": rule_reply,
            "actions": actions,
        }
        return AgentResult(
            ok=True,
            agent=self.name,
            message=final_reply,
            data=ctx.cs,
            handoff="human" if need_human else None,
            risk_level="medium" if need_human else "low",
        )

    def _should_polish(self, ctx, need_human: bool) -> bool:
        """常见短问走规则直答，复杂问题再调用远程模型。"""
        import os
        if (os.getenv('AGENTS_CS_ALWAYS_LLM') or '').lower() in {'1', 'true', 'yes'}:
            return True
        if need_human:
            return False
        intent = (ctx.intent or {}).get('intent')
        text = (ctx.user_text or '').strip()
        if intent in {'greeting', 'pay_help', 'track', 'order_status'} and len(text) <= 18:
            return False
        if len(text) <= 8 and intent in {'search', 'recommend', 'compare'}:
            return False
        return True

    def _rule_reply(
        self,
        ctx: AgentContext,
        intent,
        need_human: bool,
        knowledge_miss: bool = False,
        grounded_query: bool = False,
    ) -> str:
        if knowledge_miss:
            return "这个问题目前没有找到已确认的店铺规则，我已转人工客服确认，避免给你错误答复。"
        store_cards = [
            card for card in ((ctx.knowledge or {}).get("cards") or [])
            if card.get("kind") == "store"
        ]
        if grounded_query and store_cards:
            card = store_cards[0]
            return f"根据「{card.get('title')}」：{card.get('content')}"
        if intent == "greeting":
            return (
                "你好，我是店里的导购客服，可以帮你：\n"
                "· 有什么货\n"
                "· 怎么付钱\n"
                "· 我的单到哪了\n"
                "· 转店长"
            )
        if intent == "refund":
            return "售后请提供订单号与原因，建议转人工店长处理（本店为确认收款模式，退款走线下核对）。"
        if need_human:
            return "这件事建议转店长处理。点下面按钮打电话，或留下你的电话。"
        if (ctx.catalog or {}).get("count"):
            return f"已为你匹配 {(ctx.catalog or {}).get('count')} 件商品，可点「立即购买」下单。"
        return "已收到。可以告诉我预算或品类，例如「100元内耳机」。"

    def _llm_reply(self, ctx: AgentContext, rule_reply: str, need_human: bool):
        cards = (ctx.knowledge or {}).get("cards") or []
        knowledge_facts = knowledge_lib.knowledge_brief(cards)
        brief = {
            "user": ctx.user_text,
            "intent": ctx.intent,
            "knowledge_facts": knowledge_facts,
            "knowledge_cards": cards,
            "catalog_top": ((ctx.catalog or {}).get("items") or [])[:3],
            "promo_tips": ((ctx.promo or {}).get("tips") or [])[:3],
            "order_hint": (ctx.order or {}).get("place_order_path"),
            "orders": ((ctx.order or {}).get("orders") or [])[:3],
            "risk": ctx.risk,
            "memory": ctx.memory or {},
            "rule_reply": rule_reply,
            "need_human": need_human,
            "payment_mode": "personal_wechat_qr_manual_confirm",
        }
        system = (
            "你是中小电商的导购客服助手，语气自然、简洁、友好。"
            "knowledge_facts 是本店已确认事实的唯一来源，只能引用其中的店铺规则、品名、价格、参数、卖点与 FAQ。"
            "knowledge_facts 里没有的参数（续航、材质、尺寸、保修、发货时效等）一律回答「这个我需要帮你确认」，不要猜。"
            "不要编造不存在的优惠或物流单号。"
            "本店付款方式是个人微信收款码+备注订单号，店长人工确认后发货，不要说成官方自动扣款。"
            "引导用户点「立即购买」下单，不要声称你已经下单或已收款。"
            "若 need_human 为 true，明确建议转店长。"
            "回复用中文，控制在 120 字内，可用短列表。"
        )
        user = "上下文：\n" + json.dumps(brief, ensure_ascii=False)
        r = chat_completions(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.4,
            max_tokens=350,
        )
        if r.get("ok") and r.get("content"):
            return r
        return None
