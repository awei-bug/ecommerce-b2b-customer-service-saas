# -*- coding: utf-8 -*-
from __future__ import annotations

from abc import ABC, abstractmethod

from .types import AgentContext, AgentResult


class BaseAgent(ABC):
    name: str = "base"
    description: str = ""

    @abstractmethod
    def run(self, ctx: AgentContext) -> AgentResult:
        """只做本职；读 ctx，写回自己的字段，返回 AgentResult。"""

    def safe_run(self, ctx: AgentContext) -> AgentResult:
        try:
            ctx.add_trace(self.name, "start")
            result = self.run(ctx)
            ctx.add_trace(self.name, "end", {"ok": result.ok, "handoff": result.handoff})
            return result
        except Exception as e:
            ctx.add_trace(self.name, "error", str(e))
            return AgentResult(
                ok=False,
                agent=self.name,
                message=f"{self.name} 执行失败",
                errors=[str(e)],
                risk_level="medium",
            )
