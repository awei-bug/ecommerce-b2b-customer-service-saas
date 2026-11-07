"""Conservative, opt-in synchronisation for one explicitly configured demo tenant."""
from flask import current_app

from flask_shop import models
from flask_shop.utils.audit import write_audit
from flask_shop.utils import hub_client, hub_sync
from flask_shop.utils.tenant_query import tenant_context

PAGE_SIZE = 100
MAX_PAGES = 100
ISSUE_LIMIT = 3
ISSUE_CODES = frozenset({'missing_id', 'missing_title', 'invalid_link', 'name_conflict', 'quota', 'processing_error'})


def record_cycle(result=None, failed=False, failure_code=None):
    """Best-effort record of a completed cycle; never claim a worker is running."""
    import json
    slug = str(current_app.config.get('DATA_HUB_TENANT_SLUG') or '').strip()
    with tenant_context(disabled=True):
        tenant = models.Tenant.query.filter_by(slug=slug).first() if slug else None
    if tenant is None or tenant.data_mode != 'demo' or tenant.status != 1:
        return False
    counts = {key: int((result or {}).get(key, 0)) for key in ('received', 'created', 'updated', 'pending', 'errors')}
    state = 'failed' if failed else ('partial' if counts['errors'] else 'success')
    issues = []
    for issue in (result or {}).get('issues', [])[:ISSUE_LIMIT]:
        code = issue.get('code') if issue.get('code') in ISSUE_CODES else 'processing_error'
        issues.append({'id': str(issue.get('id') or '')[:128], 'code': code})
    data = {'status': state, **counts, 'issues': issues, 'issues_truncated': counts['errors'] > len(issues)}
    if failed:
        data['failure_code'] = failure_code if failure_code in ('hub_unavailable', 'invalid_config') else 'other'
    # write_audit caps detail at 512 characters: reduce whole entries, never truncate JSON.
    while True:
        detail = json.dumps(data, ensure_ascii=False, separators=(',', ':'))
        if len(detail) <= 512 or not data['issues']:
            break
        data['issues'].pop()
        data['issues_truncated'] = True
    return write_audit('product.hub_auto_sync', 'product', None,
                       detail,
                       tenant_id=tenant.id, actor_type='system')


def run_once():
    slug = str(current_app.config.get('DATA_HUB_TENANT_SLUG') or '').strip()
    token = str(current_app.config.get('DATA_HUB_TOKEN') or '').strip()
    if not slug or not token or not hub_client.hub_enabled():
        raise ValueError('自动同步需要配置数据中心地址、租户和令牌')
    with tenant_context(disabled=True):
        tenant = models.Tenant.query.filter_by(slug=slug).first()
    if tenant is None or tenant.data_mode != 'demo' or tenant.status != 1:
        raise ValueError('自动同步仅支持启用的同名演示租户')

    total = {'received': 0, 'created': 0, 'updated': 0, 'pending': 0, 'errors': 0, 'issues': []}
    for page in range(MAX_PAGES):
        result = hub_sync.sync_from_hub(
            tenant, limit=PAGE_SIZE, offset=page * PAGE_SIZE, publish=False,
            ack=False, safe_existing=True,
        )
        total['received'] += result['received']
        for key in ('created', 'updated', 'pending', 'errors'):
            total[key] += result['summary'][key]
        for row in result['errors']:
            if len(total['issues']) >= ISSUE_LIMIT:
                break
            total['issues'].append({'id': str(row.get('external_id') or '')[:128],
                                    'code': row.get('code') if row.get('code') in ISSUE_CODES else 'processing_error'})
        if result['received'] < PAGE_SIZE:
            return total
    raise RuntimeError('商品数量超过单轮同步上限，请检查数据中心')
