"""统一经营看板聚合接口：逐路隔离、不伪造数据、来源可见。"""
from flask_shop.unified import views


def _stub_upstreams(monkeypatch, failures=()):
    calls = []

    def fake_fetch(url, headers, timeout):
        calls.append(url)
        if any(key in url for key in failures):
            raise RuntimeError(f'上游不可用: {url}')
        if 'inventory/alerts' in url:
            return {'items': [{'product_id': '1'}], 'total_projections': 4}
        if 'inventory-drafts' in url:
            return {'data': {'items': [{'eventId': 9}, {'eventId': 8}]}}
        if '/hub/stats' in url:
            return {'total': 3, 'by_status': {'published': 3}}
        raise AssertionError(f'未预期的上游: {url}')

    monkeypatch.setattr(views, '_fetch_json', fake_fetch)
    return calls


def test_overview_requires_login(api):
    response = api['client'].get('/api/unified/overview/')
    assert response.get_json().get('status') == 401


def test_overview_aggregates_four_sources(api, monkeypatch):
    calls = _stub_upstreams(monkeypatch)
    response = api['client'].get(
        '/api/unified/overview/', headers={'token': api['seed']['token_a']}
    )
    assert response.status_code == 200
    body = response.get_json()
    assert body['status'] == 200
    data = body['data']

    assert len(calls) == 3, '三个 HTTP 上游都应被调用'
    sources = data['sources']
    assert set(sources) == {'shop', 'cross', 'content', 'hub'}
    assert all(item['status'] == 'ok' for item in sources.values())
    assert sources['shop']['orders'] >= 0
    assert sources['shop']['events'] >= 0
    assert sources['cross']['alerts'] == 1
    assert sources['content']['drafts'] == 2
    assert sources['hub']['products'] == 3
    assert data['summary']['healthy'] == 4
    assert data['summary']['total'] == 4
    assert data['tenant_id'] == api['seed']['id_a']


def test_one_upstream_failure_does_not_break_others(api, monkeypatch):
    _stub_upstreams(monkeypatch, failures=('inventory-drafts',))
    response = api['client'].get(
        '/api/unified/overview/', headers={'token': api['seed']['token_a']}
    )
    data = response.get_json()['data']
    sources = data['sources']

    assert sources['content']['status'] == 'unavailable'
    assert sources['content']['error'], '不可用原因必须对外可见'
    assert 'drafts' not in sources['content'], '不可用时不得回填演示数据'
    assert sources['cross']['status'] == 'ok'
    assert sources['hub']['status'] == 'ok'
    assert sources['shop']['status'] == 'ok'
    assert data['summary']['healthy'] == 3
    assert data['summary']['drafts'] is None
