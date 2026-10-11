# -*- coding: utf-8 -*-
"""风控安全 Agent：全链路校验。"""
from __future__ import annotations

import re

from .base import BaseAgent
from .types import AgentContext, AgentResult, AgentName, RiskLevel


class RiskAgent(BaseAgent):
    name = AgentName.RISK.value
    description = "风险校验与拦截建议"

    BLOCK_PATTERNS = [r"刷单", r"套现", r"赌博", r"色情", r"发票假", r"洗钱"]
    WARN_PATTERNS = [r"大量批发", r"私下打款不走系统", r"不要订单号"]

    def run(self, ctx: AgentContext) -> AgentResult:
        text = ctx.user_text or ""
        flags = []
        level = RiskLevel.LOW.value

        for p in self.BLOCK_PATTERNS:
            if re.search(p, text, re.I):
                flags.append({"type": "block_keyword", "pattern": p})
                level = RiskLevel.BLOCK.value

        for p in self.WARN_PATTERNS:
            if re.search(p, text, re.I):
                flags.append({"type": "warn_keyword", "pattern": p})
                if level == RiskLevel.LOW.value:
                    level = RiskLevel.MEDIUM.value

        # 业务风控
        items = (ctx.catalog or {}).get("items") or []
        for it in items[:3]:
            if it.get("stock", 0) <= 0:
                flags.append({"type": "oos", "product_id": it.get("id"), "name": it.get("name")})
                if level == RiskLevel.LOW.value:
                    level = RiskLevel.MEDIUM.value

        # 未登录查单
        intent = (ctx.intent or {}).get("intent")
        if intent in ("order_status", "track", "refund") and not ctx.customer_id:
            flags.append({"type": "auth_required", "intent": intent})

        # 付款模式提示（非拦截）
        flags.append({"type": "payment_mode", "mode": "manual_qr", "note": "人工确认收款"})

        blocked = level == RiskLevel.BLOCK.value
        ctx.risk = {
            "level": level,
            "flags": flags,
            "blocked": blocked,
            "allow_continue": not blocked,
        }

        if blocked:
            msg = "风控拦截：检测到高风险表述，已停止自动推荐下单，请转人工审核。"
        elif level == RiskLevel.MEDIUM.value:
            msg = "风控提示：存在需注意的点（缺货/未登录/异常措辞），可继续但请核实。"
        else:
            msg = "风控通过：风险较低，可继续引导下单或查单。"

        return AgentResult(
            ok=not blocked,
            agent=self.name,
            message=msg,
            data=ctx.risk,
            risk_level=level,
            handoff="human" if blocked else None,
        )
