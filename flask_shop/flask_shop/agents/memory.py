# -*- coding: utf-8 -*-
"""简单多轮会话记忆（进程内 TTL）。生产可换 Redis。"""
from __future__ import annotations

import time
from threading import Lock
from typing import Any, Dict, List, Optional

_lock = Lock()
_STORE: Dict[str, Dict[str, Any]] = {}
DEFAULT_TTL = 30 * 60  # 30 min
MAX_TURNS = 12


def _purge(now: float):
    dead = [k for k, v in _STORE.items() if v.get("exp", 0) < now]
    for k in dead:
        _STORE.pop(k, None)


def get_session(session_id: str) -> Dict[str, Any]:
    now = time.time()
    with _lock:
        _purge(now)
        s = _STORE.get(session_id)
        if not s:
            return {"turns": [], "last_products": [], "last_intent": {}}
        return {
            "turns": list(s.get("turns") or []),
            "last_products": list(s.get("last_products") or []),
            "last_intent": dict(s.get("last_intent") or {}),
        }


def save_session(
    session_id: str,
    *,
    user_text: str,
    reply: str,
    products: Optional[List[Dict[str, Any]]] = None,
    intent: Optional[Dict[str, Any]] = None,
    ttl: int = DEFAULT_TTL,
):
    now = time.time()
    with _lock:
        _purge(now)
        s = _STORE.get(session_id) or {
            "turns": [],
            "last_products": [],
            "last_intent": {},
            "exp": now + ttl,
        }
        turns = list(s.get("turns") or [])
        turns.append({"role": "user", "text": user_text, "ts": now})
        turns.append({"role": "assistant", "text": reply, "ts": now})
        s["turns"] = turns[-MAX_TURNS * 2 :]
        if products:
            s["last_products"] = products
        if intent:
            s["last_intent"] = intent
        s["exp"] = now + ttl
        _STORE[session_id] = s


def resolve_followup(user_text: str, session: Dict[str, Any]) -> Dict[str, Any]:
    """识别「买第1个/就这个」等指代。"""
    import re
    text = (user_text or "").strip()
    products = session.get("last_products") or []
    out = {"is_followup": False, "product": None, "index": None}
    if not products:
        return out
    m = re.search(r"(?:买|要|选|第)\s*([1-5一二三四五])", text)
    if not m and not re.search(r"就这个|就它|下单这个|要这个", text):
        return out
    idx = 0
    if m:
        raw = m.group(1)
        mp = {"1": 0, "2": 1, "3": 2, "4": 3, "5": 4, "一": 0, "二": 1, "三": 2, "四": 3, "五": 4}
        idx = mp.get(raw, 0)
    if idx < len(products):
        out = {"is_followup": True, "product": products[idx], "index": idx}
    return out
