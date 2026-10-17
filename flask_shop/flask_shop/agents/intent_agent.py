# -*- coding: utf-8 -*-
"""用户意图 Agent：规则解析 + OpenRouter 可选增强。"""
from __future__ import annotations

import os
import re
from typing import Any, Dict, List

from .base import BaseAgent
from .types import AgentContext, AgentResult, AgentName
from .tools.llm_client import llm_enabled, llm_json


class IntentAgent(BaseAgent):
    name = AgentName.INTENT.value
    description = "解析用户购物/售后/查单意图"

    # 规则按「业务信号强度」排序：越靠前优先级越高（primary = hits[0]）。
    # search 放在倒数第二是刻意设计：它的触发词（有没有/看看/找）过于宽泛，
    # 如果排在 cs/售后 之前，会抢走「有没有人工」「退货有没有问题」这类真意图。
    # 评测驱动迭代（2026-10-17）：扩到 138 条难例后基线 65%，48 条误判中 39 条
    # 漏进 search；本次通过重排 + 补口语规则把误判降到个位数。
    INTENT_RULES = [
        # 商家端（商城渠道会改写/拦截，不参与顾客意图）
        ("list_product", [r"帮我上架", r"上架一款", r"上架一个", r"^上架", r"发布商品", r"新品上架"]),
        ("ops", [r"今日", r"报表", r"转化", r"库存预警", r"运营", r"统计", r"看板", r"经营"]),
        # 资金/售后最紧，其次订单物流
        ("pay_help", [r"怎么付款", r"如何付款", r"付款后", r"收款码", r"收款", r"转账", r"支付", r"扫码", r"付钱", r"货到付款", r"花呗", r"定金", r"分期", r"信用卡", r"白条", r"支付宝", r"微信支付"]),
        ("refund", [r"退款", r"退货", r"售后", r"换货", r"换一件", r"尺码不合适", r"可以退", r"能退", r"想退", r"取消订单", r"不想要了", r"无理由", r"质量问题", r"瑕疵", r"没收到", r"退回来", r"退货地址"]),
        ("order_status", [r"我的订单", r"订单状态", r"订单.*到哪", r"买了什么", r"买的东西", r"待付款", r"查订单", r"查下订单", r"查.*订单", r"我的单", r"几单", r"订单.*确认", r"订单进展"]),
        ("track", [r"物流", r"快递", r"发货", r"到哪了", r"到哪儿", r"运单", r"什么时候能收到", r"能到", r"单号", r"没发货"]),
        ("cs", [r"客服", r"人工", r"投诉", r"纠纷", r"联系", r"转店长", r"几点.*(?:下班|关门)", r"反映", r"优惠券"]),
        # 选品/对比
        ("compare", [r"对比", r"哪个好", r"哪个更", r"更适合", r"区别", r"比较", r"怎么选", r"这款和那款", r"这两件", r"性价比", r"差在哪", r"比.*(?:便宜|贵)"]),
        ("recommend", [r"推荐", r"买什么", r"有什么好", r"帮我选", r"种草", r"有什么货", r"穿什么", r"约会", r"搭一套", r"搭配", r"值得买", r"爆款", r"给我推", r"卖得最好", r"送人"]),
        # 商品检索（倒数第二，兜底）
        ("search", [r"有没有", r"找", r"搜索", r"看看", r"耳机", r"键盘", r"衣服", r"咖啡", r"台灯", r"枕头", r"手环"]),
        # 寒暄（信号最弱，放最后）
        ("greeting", [r"你好", r"您好", r"在吗", r"有人吗", r"在不在", r"hello", r"hi", r"哈喽", r"早上好", r"中午好", r"下午好", r"晚上好", r"谢谢"]),
    ]

    LABELS = {
        "search": "商品检索",
        "recommend": "选品推荐",
        "compare": "商品对比",
        "pay_help": "付款咨询",
        "order_status": "订单查询",
        "track": "物流查询",
        "refund": "售后诉求",
        "cs": "客服会话",
        "ops": "运营分析",
        "list_product": "商品上架",
        "greeting": "寒暄",
    }

    NEXT = {
        "search": "catalog",
        "recommend": "catalog",
        "compare": "catalog",
        "pay_help": "order",
        "order_status": "order",
        "track": "order",
        "refund": "cs",
        "cs": "cs",
        "ops": "ops",
        "list_product": "listing",
        "greeting": "cs",
    }

    def run(self, ctx: AgentContext) -> AgentResult:
        text = (ctx.user_text or "").strip()
        intent = self._parse_rules(text)
        # The merchant ops endpoint has a deliberately narrow contract: every
        # non-listing request is an operations query. Keep it deterministic so
        # an unavailable external model cannot block the merchant console.
        if ctx.channel == "admin_ops" and intent.get("intent") != "list_product":
            intent["intent"] = "ops"
            intent["confidence"] = max(float(intent.get("confidence") or 0), 0.95)
            intent["raw_hits"] = list(dict.fromkeys([*(intent.get("raw_hits") or []), "ops"]))
        if intent.get("intent") == "list_product" and ctx.channel != "admin_ops":
            intent["intent"] = "cs"
            intent["blocked_listing"] = True

        llm_meta = {"used": False}
        if ctx.channel != "admin_ops" and llm_enabled() and text and self._should_refine(intent, text):
            refined = self._refine_with_llm(text, intent)
            if refined:
                intent.update(refined)
                llm_meta = {"used": True, "model": refined.get("_model")}

        if intent.get("intent") == "list_product" and ctx.channel != "admin_ops":
            intent["intent"] = "cs"
            intent["blocked_listing"] = True
        intent["label"] = self.LABELS.get(intent.get("intent"), intent.get("intent"))
        intent["next"] = self.NEXT.get(intent.get("intent"), "cs")
        intent["need_login"] = intent.get("intent") in (
            "order_status", "track", "refund", "pay_help",
        )
        intent["llm"] = llm_meta
        ctx.intent = intent

        msg = f"已理解意图：{intent.get('label')}（置信 {intent.get('confidence', 0):.2f}）"
        if llm_meta.get("used"):
            msg += f" · LLM:{llm_meta.get('model') or 'openrouter'}"
        return AgentResult(ok=True, agent=self.name, message=msg, data=intent, handoff=intent.get("next"))

    def _should_refine(self, intent: Dict[str, Any], text: str) -> bool:
        """高置信度单意图直接走规则，减少一次远程模型往返。"""
        if (os.getenv('AGENTS_INTENT_ALWAYS_LLM') or '').lower() in {'1', 'true', 'yes'}:
            return True
        if len(text) <= 18 and float(intent.get('confidence') or 0) >= 0.67 and len(intent.get('raw_hits') or []) == 1:
            return False
        return True

    def _parse_rules(self, text: str) -> Dict[str, Any]:
        t = text.lower()
        hits: List[str] = []
        for name, patterns in self.INTENT_RULES:
            for p in patterns:
                if re.search(p, text, re.I) or re.search(p, t, re.I):
                    hits.append(name)
                    break

        budget = None
        m = re.search(r"(?:不超过|低于|预算|以内|小于)\s*(\d+(?:\.\d+)?)\s*元?", text)
        if not m:
            m = re.search(r"(\d+(?:\.\d+)?)\s*元\s*(?:以内|以下|内)", text)
        if not m:
            m = re.search(r"(\d+(?:\.\d+)?)\s*块钱?", text)
        if m:
            budget = float(m.group(1))

        stop = set(list("的了吗呢啊吧么在吗") + ["我要", "帮我", "一个", "有没有", "看看", "有什么货", "怎么付钱", "转店长"])
        tokens = re.findall(r"[\u4e00-\u9fffA-Za-z0-9]+", text)
        keywords = [w for w in tokens if w not in stop and 2 <= len(w) <= 8 and not w.isdigit()][:6]
        for noun in ["耳机", "键盘", "手环", "咖啡", "台灯", "枕头", "衣服", "男装", "T恤", "托特包", "包",
                     "衬衫", "卫衣", "短袖", "外套", "夹克", "大衣", "裤", "牛仔", "冲锋衣", "毛衣",
                     "风衣", "背心", "鞋", "帽"]:
            if noun in text and noun not in keywords:
                keywords.insert(0, noun)
        keywords = keywords[:6]

        primary = hits[0] if hits else ("search" if keywords else "greeting")
        if primary == "search" and not keywords and ("推荐" in text):
            primary = "recommend"

        conf = 0.55 + 0.12 * min(len(set(hits)), 3)
        if budget is not None:
            conf = min(0.95, conf + 0.08)

        return {
            "intent": primary,
            "confidence": round(min(conf, 0.95), 2),
            "keywords": keywords,
            "budget_max": budget,
            "raw_hits": hits,
        }


    INTENT_ALIASES = {
        "search": "search",
        "检索": "search",
        "搜索": "search",
        "找商品": "search",
        "recommend": "recommend",
        "推荐": "recommend",
        "选品": "recommend",
        "耳机推荐": "recommend",
        "商品推荐": "recommend",
        "compare": "compare",
        "对比": "compare",
        "pay_help": "pay_help",
        "付款": "pay_help",
        "支付": "pay_help",
        "order_status": "order_status",
        "订单": "order_status",
        "查订单": "order_status",
        "track": "track",
        "物流": "track",
        "refund": "refund",
        "售后": "refund",
        "退款": "refund",
        "cs": "cs",
        "客服": "cs",
        "ops": "ops",
        "运营": "ops",
        "list_product": "list_product",
        "上架": "list_product",
        "greeting": "greeting",
        "寒暄": "greeting",
        "你好": "greeting",
    }

    def _normalize_intent(self, raw) -> str | None:
        if raw is None:
            return None
        s = str(raw).strip().lower()
        if s in self.LABELS:
            return s
        # direct alias
        if raw in self.INTENT_ALIASES:
            return self.INTENT_ALIASES[raw]
        if s in self.INTENT_ALIASES:
            return self.INTENT_ALIASES[s]
        # fuzzy contains
        for k, v in self.INTENT_ALIASES.items():
            if k in str(raw):
                return v
        return None

    def _clean_keywords(self, kws, text: str) -> list:
        out = []
        stop = set(["有没有", "推荐一下", "平价推荐", "入门级", "左右", "一个", "帮我", "看看", "有什么货", "怎么付钱", "转店长"])
        for w in kws or []:
            w = str(w).strip()
            if not w or w in stop or w.isdigit():
                continue
            # strip 元
            w2 = re.sub(r"\d+元?", "", w).strip()
            if len(w2) >= 2:
                out.append(w2)
            elif len(w) >= 2 and not any(ch.isdigit() for ch in w):
                out.append(w)
        # ensure product nouns from text
        for noun in ["耳机", "键盘", "手环", "咖啡", "台灯", "枕头", "衣服", "T恤", "包",
                     "衬衫", "卫衣", "短袖", "外套", "夹克", "大衣", "裤", "牛仔", "冲锋衣", "毛衣",
                     "风衣", "背心", "鞋", "帽"]:
            if noun in text and noun not in out:
                out.insert(0, noun)
        # unique preserve order
        seen = set()
        uniq = []
        for w in out:
            if w not in seen:
                seen.add(w)
                uniq.append(w)
        return uniq[:6]

    def _refine_with_llm(self, text: str, base: Dict[str, Any]) -> Dict[str, Any] | None:
        system = (
            "你是电商意图分类器。必须输出 JSON 对象，字段：\n"
            'intent 只能是英文枚举之一: search, recommend, compare, pay_help, order_status, track, refund, cs, ops, list_product, greeting\n'
            "keywords: 商品品类中文词数组，如 [\"耳机\"]，不要整句\n"
            "budget_max: 数字或 null\n"
            "confidence: 0 到 1\n"
            "不要输出其它 intent 值。"
        )
        user = f"用户说：{text}\n规则初判：{base}"
        r = llm_json(system, user, temperature=0.0)
        if not r.get("ok"):
            return None
        data = r.get("data") or {}
        intent = self._normalize_intent(data.get("intent") or base.get("intent"))
        if not intent:
            return None
        kws = self._clean_keywords(data.get("keywords") or base.get("keywords") or [], text)
        out = {
            "intent": intent,
            "keywords": kws,
            "budget_max": data.get("budget_max", base.get("budget_max")),
            "confidence": float(data.get("confidence") or base.get("confidence") or 0.7),
            "_model": r.get("model"),
        }
        if out["budget_max"] is not None:
            try:
                out["budget_max"] = float(out["budget_max"])
            except Exception:
                out["budget_max"] = base.get("budget_max")
        return out
