# -*- coding: utf-8 -*-
"""Agent 协议类型：统一消息与上下文，避免各 Agent 私自约定。"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Optional
import time
import uuid


class AgentName(str, Enum):
    INTENT = "intent"
    CATALOG = "catalog"
    PROMO = "promo"
    ORDER = "order"
    CS = "cs"
    OPS = "ops"
    RISK = "risk"
    LISTING = "listing"
    ORCHESTRATOR = "orchestrator"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    BLOCK = "block"


@dataclass
class AgentContext:
    """一次协作会话的共享上下文（只增不乱改核心字段）。"""
    session_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    tenant_id: Optional[int] = None
    tenant_slug: str = "demo"
    customer_id: Optional[int] = None
    staff_id: Optional[int] = None
    channel: str = "mall_chat"  # mall_chat | admin_ops | api
    user_text: str = ""
    locale: str = "zh-CN"
    # 各 Agent 写入的结构化中间结果
    intent: Dict[str, Any] = field(default_factory=dict)
    catalog: Dict[str, Any] = field(default_factory=dict)
    promo: Dict[str, Any] = field(default_factory=dict)
    order: Dict[str, Any] = field(default_factory=dict)
    cs: Dict[str, Any] = field(default_factory=dict)
    ops: Dict[str, Any] = field(default_factory=dict)
    risk: Dict[str, Any] = field(default_factory=dict)
    # 数据中心商品知识卡，客服应答的唯一可引用事实集
    knowledge: Dict[str, Any] = field(default_factory=dict)
    # 持久化的顾客/会话记忆；不存放未经确认的商品事实
    memory: Dict[str, Any] = field(default_factory=dict)
    # 轨迹
    trace: List[Dict[str, Any]] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    def add_trace(self, agent: str, action: str, detail: Any = None):
        self.trace.append({
            "ts": time.time(),
            "agent": agent,
            "action": action,
            "detail": detail,
        })

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d


@dataclass
class AgentResult:
    ok: bool = True
    agent: str = ""
    message: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    handoff: Optional[str] = None  # 建议下一 Agent 或 human
    risk_level: str = RiskLevel.LOW.value
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
