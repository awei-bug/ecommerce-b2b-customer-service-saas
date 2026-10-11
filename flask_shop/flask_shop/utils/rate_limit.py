# -*- coding: utf-8 -*-
"""简单进程内滑动窗口限流。"""
from __future__ import annotations

import time
from collections import defaultdict, deque
from functools import wraps
from threading import Lock

from flask import g, jsonify, request

_lock = Lock()
_buckets = defaultdict(deque)


def _client_key(prefix: str) -> str:
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "unknown").split(",")[0].strip()
    extra = ""
    try:
        if getattr(g, "customer_id", None):
            extra = f":c{g.customer_id}"
        elif getattr(g, "staff_id", None):
            extra = f":s{g.staff_id}"
    except Exception:
        pass
    return f"{prefix}:{ip}{extra}"


def rate_limit(max_calls: int = 30, per_seconds: int = 60, prefix: str = "rl"):
    def deco(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            key = _client_key(prefix)
            now = time.time()
            with _lock:
                q = _buckets[key]
                while q and q[0] <= now - per_seconds:
                    q.popleft()
                if len(q) >= max_calls:
                    return jsonify({
                        "status": 429,
                        "msg": f"请求过于频繁，请 {per_seconds} 秒后再试",
                    }), 429
                q.append(now)
            return fn(*args, **kwargs)
        return wrapper
    return deco
