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
_MAX_BUCKETS = 10000
_CLEANUP_INTERVAL = 10
_last_cleanup = 0.0


def _client_key(prefix: str) -> str:
    ip = request.remote_addr or "unknown"
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
            global _last_cleanup
            key = _client_key(f'{prefix}:{max_calls}:{per_seconds}')
            now = time.monotonic()
            with _lock:
                if now - _last_cleanup >= _CLEANUP_INTERVAL:
                    for old_key, old_queue in list(_buckets.items()):
                        if not old_queue or old_queue[-1] <= now:
                            del _buckets[old_key]
                    _last_cleanup = now
                if key not in _buckets and len(_buckets) >= _MAX_BUCKETS:
                    return jsonify({
                        "status": 503,
                        "msg": "服务繁忙，请稍后再试",
                    }), 503
                q = _buckets[key]
                while q and q[0] <= now:
                    q.popleft()
                if len(q) >= max_calls:
                    return jsonify({
                        "status": 429,
                        "msg": f"请求过于频繁，请 {per_seconds} 秒后再试",
                    }), 429
                q.append(now + per_seconds)
            return fn(*args, **kwargs)
        return wrapper
    return deco
