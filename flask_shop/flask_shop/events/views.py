"""内网领域事件增量端点。

下游按自增 id 拉取，自带水位与幂等能力。默认关闭，必须同时配置
EVENTS_API_ENABLED 与 EVENTS_API_TOKEN，缺任一项直接拒绝，避免
出现 data-hub 那种空配置全开放的情况。
"""
import hmac
import os

from flask import current_app, request

from flask_shop import models
from flask_shop.events import events_bp
from flask_shop.utils.tenant_query import tenant_context


def _check_events_token():
    if not current_app.config.get('EVENTS_API_ENABLED', False):
        return {'status': 403, 'msg': '事件接口未启用'}, 403
    expected = (current_app.config.get('EVENTS_API_TOKEN')
                or os.getenv('EVENTS_API_TOKEN') or '')
    if not expected:
        return {'status': 503, 'msg': '未配置 EVENTS_API_TOKEN，拒绝提供事件'}, 503
    got = request.headers.get('X-Events-Token') or ''
    if not hmac.compare_digest(str(got).encode('utf-8'), str(expected).encode('utf-8')):
        return {'status': 401, 'msg': '事件令牌无效'}, 401
    return None, None


def _non_negative_int(raw, default):
    if raw is None:
        return default, True
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None, False
    return max(value, 0), True


@events_bp.route('/events', methods=['GET'])
def list_domain_events():
    err, code = _check_events_token()
    if err:
        return err, code

    after, ok = _non_negative_int(request.args.get('after'), 0)
    if not ok:
        return {'status': 400, 'msg': 'after 必须是非负整数'}, 400

    raw_limit = request.args.get('limit')
    limit, ok = _non_negative_int(raw_limit, 100)
    if not ok:
        return {'status': 400, 'msg': 'limit 必须是非负整数'}, 400
    max_limit = int(current_app.config.get('EVENTS_API_MAX_LIMIT', 500) or 500)
    limit = max(1, min(limit, max_limit))

    raw_tenant = request.args.get('tenant_id')
    tenant_id = None
    if raw_tenant is not None:
        try:
            tenant_id = int(raw_tenant)
        except (TypeError, ValueError):
            return {'status': 400, 'msg': 'tenant_id 必须是整数'}, 400

    # DomainEvent 含 tenant_id，会被 before_compile 自动加租户条件。
    # 内网端点需要跨租户读取，因此在 disabled 上下文内查询。
    with tenant_context(disabled=True):
        query = models.DomainEvent.query.filter(models.DomainEvent.id > after)
        if tenant_id is not None:
            query = query.filter_by(tenant_id=tenant_id)
        rows = query.order_by(models.DomainEvent.id.asc()).limit(limit).all()
        items = [row.to_dict() for row in rows]

    next_cursor = items[-1]['id'] if items else after
    return {
        'status': 200,
        'data': {
            'events': items,
            'next_cursor': next_cursor,
            'has_more': len(items) == limit,
        },
    }
