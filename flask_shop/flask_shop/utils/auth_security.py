# -*- coding: utf-8 -*-
"""登录防爆破：持久化账户和来源地址失败计数。"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta

from flask import current_app, request

from flask_shop import db, models


def _client_ip() -> str:
    # 只信任反向代理已经规范化的第一段地址；生产 Nginx 会覆盖该头。
    forwarded = request.headers.get('X-Forwarded-For', '')
    return (forwarded.split(',')[0].strip() if forwarded else (request.remote_addr or 'unknown'))[:128]


def _hash(value: str) -> str:
    return hashlib.sha256(str(value or '').strip().lower().encode('utf-8')).hexdigest()


def _keys(username: str, tenant_slug: str):
    keys = [('ip', _hash(_client_ip()))]
    if tenant_slug:
        account = f"{tenant_slug}:{username or '-'}"
        keys.insert(0, ('account', _hash(account)))
    return keys


def _row(scope, key_hash):
    return models.LoginThrottle.query.filter_by(scope=scope, key_hash=key_hash).first()


def login_lock_status(username: str, tenant_slug: str) -> int:
    """返回剩余锁定秒数；0 表示可继续尝试。"""
    now = datetime.now()
    remaining = 0
    for scope, key_hash in _keys(username, tenant_slug):
        row = _row(scope, key_hash)
        if row and row.locked_until and row.locked_until > now:
            remaining = max(remaining, int((row.locked_until - now).total_seconds()) + 1)
    return remaining


def record_login_failure(username: str, tenant_slug: str) -> int:
    now = datetime.now()
    account_limit = int(current_app.config.get('LOGIN_ACCOUNT_FAILURE_LIMIT', 5))
    ip_limit = int(current_app.config.get('LOGIN_IP_FAILURE_LIMIT', 20))
    lock_minutes = int(current_app.config.get('LOGIN_LOCK_MINUTES', 15))
    remaining = 0
    for scope, key_hash in _keys(username, tenant_slug):
        row = _row(scope, key_hash)
        if not row:
            row = models.LoginThrottle(scope=scope, key_hash=key_hash, failed_count=0)
            db.session.add(row)
        if row.last_failed_at and (now - row.last_failed_at).total_seconds() > 900:
            row.failed_count = 0
            row.first_failed_at = now
        row.failed_count = int(row.failed_count or 0) + 1
        row.first_failed_at = row.first_failed_at or now
        row.last_failed_at = now
        limit = account_limit if scope == 'account' else ip_limit
        if row.failed_count >= limit:
            row.locked_until = now + timedelta(minutes=lock_minutes)
        if row.locked_until and row.locked_until > now:
            remaining = max(remaining, int((row.locked_until - now).total_seconds()) + 1)
    db.session.commit()
    return remaining


def clear_login_failures(username: str, tenant_slug: str) -> None:
    account_key = _hash(f"{tenant_slug or '-'}:{username or '-'}")
    row = _row('account', account_key)
    if row:
        row.failed_count = 0
        row.first_failed_at = None
        row.last_failed_at = None
        row.locked_until = None
        db.session.commit()
