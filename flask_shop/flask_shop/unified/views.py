"""统一经营看板的服务端聚合。

设计约束
- 同源单请求：前端只调 /api/unified/overview/，不直接接触 8000 / 3100 / 8120。
- 逐路隔离：每个上游独立超时，失败只把该路标记为 unavailable，不影响其余三路。
- 不伪造数据：任何一路不可用时返回 null，不回填演示值。
- 上游地址与超时全部可配置，避免换环境就整体失效。
"""
from __future__ import annotations

import os
import time
from datetime import datetime

import requests
from flask import current_app, request

from flask_shop import models
from flask_shop.unified import unified_bp
from flask_shop.utils.money import money_float
from flask_shop.utils.tenant import require_tenant_id
from flask_shop.utils.tenant_query import tenant_context
from flask_shop.utils.token import login_required


def _cfg(name: str, default: str) -> str:
    return str(current_app.config.get(name) or os.getenv(name) or default).rstrip('/')


def _timeout() -> float:
    try:
        return float(current_app.config.get('UNIFIED_OVERVIEW_TIMEOUT') or 2.5)
    except (TypeError, ValueError):
        return 2.5


def _incoming_token() -> str:
    """复用当前商家会话，不额外签发或缓存凭证。"""
    raw = request.headers.get('Authorization') or ''
    if raw.lower().startswith('bearer '):
        return raw[7:].strip()
    return (request.headers.get('token') or '').strip()


def _elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


def _ok(data: dict, started: float) -> dict:
    return {'status': 'ok', 'latency_ms': _elapsed_ms(started), 'error': None, **data}


def _failed(error: str, started: float) -> dict:
    return {'status': 'unavailable', 'latency_ms': _elapsed_ms(started),
            'error': str(error)[:160]}


def _fetch_json(url: str, headers: dict, timeout: float) -> dict:
    """只接受 200 + 合法 JSON；其余一律按不可用处理。"""
    response = requests.get(url, headers=headers, timeout=timeout)
    if response.status_code != 200:
        raise RuntimeError(f'上游返回 {response.status_code}')
    return response.json()


def _shop_source(tenant_id: int) -> dict:
    started = time.monotonic()
    try:
        with tenant_context(tenant_id=tenant_id):
            order_count = models.Order.query.filter_by(tenant_id=tenant_id).count()
            event_count = models.DomainEvent.query.filter_by(tenant_id=tenant_id).count()
            recent = (models.Order.query.filter_by(tenant_id=tenant_id)
                      .order_by(models.Order.id.desc()).limit(5).all())
            rows = []
            for order in recent:
                created = getattr(order, 'create_time', None)
                rows.append({
                    'order_no': order.order_no,
                    'price': money_float(order.price),
                    'status': order.status,
                    'created_at': created.strftime('%Y-%m-%d %H:%M:%S')
                    if isinstance(created, datetime) else '',
                })
        return _ok({'orders': order_count, 'events': event_count, 'recent_orders': rows}, started)
    except Exception as exc:
        return _failed(str(exc), started)


def _cross_source(token: str) -> dict:
    started = time.monotonic()
    try:
        base = _cfg('UNIFIED_CROSS_API_URL', 'http://127.0.0.1:8000')
        payload = _fetch_json(
            f'{base}/api/v1/inventory/alerts?threshold=25',
            {'Authorization': f'Bearer {token}'}, _timeout(),
        )
        return _ok({
            'alerts': len(payload.get('items') or []),
            'total_projections': payload.get('total_projections') or 0,
            'items': (payload.get('items') or [])[:5],
        }, started)
    except Exception as exc:
        return _failed(str(exc), started)


def _content_source(token: str) -> dict:
    started = time.monotonic()
    try:
        base = _cfg('UNIFIED_CONTENT_API_URL', 'http://127.0.0.1:3100')
        payload = _fetch_json(
            f'{base}/api/inventory-drafts?limit=5',
            {'Authorization': f'Bearer {token}'}, _timeout(),
        )
        items = ((payload.get('data') or {}).get('items')) or []
        return _ok({'drafts': len(items), 'items': items[:5]}, started)
    except Exception as exc:
        return _failed(str(exc), started)


def _hub_source() -> dict:
    started = time.monotonic()
    try:
        base = _cfg('UNIFIED_HUB_API_URL', 'http://127.0.0.1:8120')
        slug = _cfg('DATA_HUB_TENANT_SLUG', 'demo')
        token = str(current_app.config.get('DATA_HUB_TOKEN') or os.getenv('DATA_HUB_TOKEN') or '')
        payload = _fetch_json(
            f'{base}/hub/stats?tenant={slug}',
            {'X-Hub-Tenant': slug, 'X-Hub-Token': token}, _timeout(),
        )
        return _ok({
            'products': payload.get('total') or 0,
            'by_status': payload.get('by_status') or {},
        }, started)
    except Exception as exc:
        return _failed(str(exc), started)


@unified_bp.route('/overview/', methods=['GET'])
@login_required
def unified_overview():
    """四路真实数据聚合。每一路的 status 与 latency_ms 都对外可见。"""
    tenant_id = require_tenant_id()
    token = _incoming_token()

    sources = {
        'shop': _shop_source(tenant_id),
        'cross': _cross_source(token),
        'content': _content_source(token),
        'hub': _hub_source(),
    }
    summary = {
        'orders': sources['shop'].get('orders'),
        'alerts': sources['cross'].get('alerts'),
        'drafts': sources['content'].get('drafts'),
        'hub_products': sources['hub'].get('products'),
        'healthy': sum(1 for item in sources.values() if item['status'] == 'ok'),
        'total': len(sources),
    }
    return {
        'status': 200,
        'msg': 'ok',
        'data': {
            'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'tenant_id': tenant_id,
            'sources': sources,
            'summary': summary,
        },
    }
