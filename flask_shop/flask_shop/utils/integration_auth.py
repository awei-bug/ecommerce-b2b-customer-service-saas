# -*- coding: utf-8 -*-
"""机器对机器集成凭证。

用于内容平台（content_create）直推商品成品包到商城，绕过员工 JWT 登录。

设计约束：
- token 与租户绑定，一个 token 只能写它被授权的租户，不允许凭 token 遍历租户
- 使用 compare_digest 做常量时间比较，避免时序侧信道
- 未配置任何 token 时本机制整体关闭，绝不退化成匿名可写
"""
from __future__ import annotations

import secrets

from flask import current_app, request

from flask_shop.utils.tenant import bind_tenant, load_tenant

TOKEN_HEADER = 'X-Integration-Token'
SLUG_HEADER = 'X-Tenant-Slug'


def _parse_token_map(raw: str) -> dict:
    """解析 'slug1:token1,slug2:token2' 形式的配置。"""
    mapping = {}
    for chunk in (raw or '').split(','):
        chunk = chunk.strip()
        if not chunk or ':' not in chunk:
            continue
        slug, _, token = chunk.partition(':')
        slug = slug.strip()
        token = token.strip()
        if slug and token:
            mapping[slug] = token
    return mapping


def configured_tokens() -> dict:
    raw = current_app.config.get('INTEGRATION_TOKENS') or ''
    if isinstance(raw, dict):
        return {str(k): str(v) for k, v in raw.items() if k and v}
    return _parse_token_map(str(raw))


def integration_enabled() -> bool:
    return bool(configured_tokens())


def resolve_integration_tenant():
    """校验集成凭证并绑定租户。失败返回 None。"""
    tokens = configured_tokens()
    if not tokens:
        return None

    token = (request.headers.get(TOKEN_HEADER) or '').strip()
    slug = (request.headers.get(SLUG_HEADER) or '').strip()
    if not token or not slug:
        return None

    expected = tokens.get(slug)
    if not expected:
        return None
    if not secrets.compare_digest(token, expected):
        return None

    tenant = load_tenant(tenant_slug=slug)
    if not tenant:
        return None

    bind_tenant(tenant)
    return tenant
