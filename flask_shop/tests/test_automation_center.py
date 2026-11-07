from datetime import date
import time
import pytest

from flask_shop import db, models
from flask_shop.utils.token import generate_token
from flask_shop.utils.tenant_query import tenant_context


def _headers(seed, key='token_a'):
    return {'token': seed[key]}


def _enable_demo_tenant(app, tenant_id):
    with app.app_context(), tenant_context(disabled=True):
        db.session.get(models.Tenant, tenant_id).data_mode = 'demo'
        db.session.commit()
    db.session.expire_all()


def test_live_tenant_cannot_start_automatic_listing(api, app):
    seed, client = api['seed'], api['client']
    for scope in ('create_new', 'missing_image', 'all_products'):
        response = client.post('/api/automation/creative/auto/start/', json={
            'scope': scope, 'publish': True,
        }, headers=_headers(seed)).get_json()
        assert response['status'] == 503
    with app.app_context(), tenant_context(disabled=True):
        assert models.AutomationRun.query.filter_by(tenant_id=seed['id_a']).count() == 0
        assert db.session.get(models.Product, seed['product_a'].id).big_img is None


def test_creative_operations_require_product_permissions(api, app, monkeypatch):
    seed, client = api['seed'], api['client']
    with app.app_context(), tenant_context(disabled=True):
        role = models.Role(tenant_id=seed['id_a'], name='仅客服', perm_codes='["service:read"]')
        db.session.add(role)
        db.session.flush()
        user = models.User(tenant_id=seed['id_a'], name='service_only', role_id=role.id)
        db.session.add(user)
        db.session.flush()
        token = generate_token({'typ': 'merchant', 'staff_id': user.id, 'tenant_id': seed['id_a']})
        db.session.commit()
        product_id = seed['product_a'].id

    def unexpected_provider_call(*args, **kwargs):
        raise AssertionError('unauthorized requests must not invoke image generation')

    monkeypatch.setattr('flask_shop.agents.tools.agnes_client.generate_image', unexpected_provider_call)
    headers = {'token': token}
    requests = [
        ('post', '/api/automation/creative/generate/', {'product_id': product_id, 'generate_image': True}),
        ('post', '/api/automation/creative/apply/', {'product_id': product_id, 'image': {'b64_json': 'invalid'}}),
        ('post', '/api/automation/creative/auto/start/', {'scope': 'missing_image'}),
        ('post', '/api/automation/creative/auto/1/stop/', {}),
        ('get', '/api/automation/creative/auto/1/', None),
        ('get', '/api/automation/creative/auto/current/', None),
        ('get', '/api/automation/overview/', None),
        ('get', '/api/automation/rules/', None),
        ('post', '/api/automation/rules/', {'name': '不应创建', 'module_code': 'listing'}),
    ]
    for method, path, payload in requests:
        response = client.open(path, method=method.upper(), headers=headers, json=payload)
        assert response.get_json()['status'] == 403, path
    with app.app_context(), tenant_context(disabled=True):
        assert models.AutomationRun.query.filter_by(tenant_id=seed['id_a']).count() == 0
        assert models.AutomationRule.query.filter_by(tenant_id=seed['id_a']).count() == 0
        assert db.session.get(models.Product, product_id).big_img is None


@pytest.fixture
def legacy_automation(monkeypatch):
    monkeypatch.setattr('flask_shop.automation.views.FROZEN_MODULES', frozenset())


def test_frozen_modules_are_hidden_and_cannot_run_or_mutate(api, app):
    seed, client = api['seed'], api['client']
    with app.app_context(), tenant_context(disabled=True):
        frozen_rule = models.AutomationRule(
            tenant_id=seed['id_a'], module_code='finance', name='历史财务规则', status='enabled',
        )
        db.session.add(frozen_rule)
        db.session.commit()
        rule_id = frozen_rule.id
    overview = client.get('/api/automation/overview/', headers=_headers(seed)).get_json()
    assert overview['status'] == 200
    assert overview['data']['finance'] is None
    assert {row['code'] for row in overview['data']['modules']}.isdisjoint({'finance', 'ads', 'competitor'})
    rules = client.get('/api/automation/rules/', headers=_headers(seed)).get_json()['data']
    assert {row['module_code'] for row in rules}.isdisjoint({'finance', 'ads', 'competitor'})
    requests = [
        ('GET', '/api/automation/campaigns/', None),
        ('POST', '/api/automation/campaigns/', {'campaign_name': '不应创建'}),
        ('GET', '/api/automation/competitors/', None),
        ('POST', '/api/automation/competitors/', {'competitor_name': '不应创建'}),
        ('POST', '/api/automation/competitors/1/scan/', {}),
        ('POST', '/api/automation/rules/', {'name': '不应创建', 'module_code': 'ads'}),
        ('PUT', f'/api/automation/rules/{rule_id}/', {'name': '不应修改'}),
        ('POST', f'/api/automation/rules/{rule_id}/run/', {}),
    ]
    for method, path, payload in requests:
        assert client.open(path, method=method, json=payload, headers=_headers(seed)).get_json()['status'] == 503
    with app.app_context(), tenant_context(disabled=True):
        assert db.session.get(models.AutomationRule, rule_id).name == '历史财务规则'
        assert models.AutomationRun.query.filter_by(rule_id=rule_id).count() == 0
        assert models.AdCampaignDaily.query.filter_by(tenant_id=seed['id_a']).count() == 0
        assert models.CompetitorMonitor.query.filter_by(tenant_id=seed['id_a']).count() == 0


def test_automation_overview_bootstraps_eight_modules(api, legacy_automation):
    client, seed = api['client'], api['seed']
    response = client.get('/api/automation/overview/?days=30', headers=_headers(seed))
    body = response.get_json()

    assert body['status'] == 200
    assert len(body['data']['modules']) == 8
    assert body['data']['automation']['total'] == 8
    assert set(body['data']['finance']['source_status']) == {'orders', 'payments', 'refunds', 'ads'}
    assert body['data']['finance']['assumptions']['cost_rate'] == 0.55

    # 重复首访不会重复播种默认流程。
    again = client.get('/api/automation/rules/', headers=_headers(seed)).get_json()
    assert len(again['data']) == 8


def test_campaign_data_is_tenant_isolated_and_drives_roas(api, legacy_automation):
    client, seed = api['client'], api['seed']
    payload = {
        'record_date': date.today().isoformat(),
        'platform': 'douyin',
        'campaign_name': 'A-新品计划',
        'spend': 100,
        'revenue': 260,
        'orders': 3,
        'clicks': 80,
        'impressions': 2000,
    }
    saved = client.post('/api/automation/campaigns/', json=payload, headers=_headers(seed)).get_json()
    assert saved['status'] == 200
    assert saved['data']['roas'] == 2.6

    own = client.get('/api/automation/campaigns/', headers=_headers(seed)).get_json()['data']
    other = client.get('/api/automation/campaigns/', headers=_headers(seed, 'token_b')).get_json()['data']
    assert [x['campaign_name'] for x in own] == ['A-新品计划']
    assert other == []


def test_rule_run_writes_observable_log(api, legacy_automation):
    client, seed = api['client'], api['seed']
    rules = client.get('/api/automation/rules/', headers=_headers(seed)).get_json()['data']
    finance_rule = next(x for x in rules if x['module_code'] == 'finance')

    result = client.post(
        f'/api/automation/rules/{finance_rule["id"]}/run/',
        headers=_headers(seed),
    ).get_json()

    assert result['status'] == 200
    assert result['data']['status'] == 'success'
    assert '经营利润' in result['data']['summary']
    with api['client'].application.app_context():
        with tenant_context(disabled=True):
            row = models.AutomationRun.query.filter_by(tenant_id=seed['id_a']).first()
            assert row is not None
            assert row.status == 'success'


def test_competitor_scan_detects_price_drop(api, legacy_automation):
    client, seed = api['client'], api['seed']
    created = client.post('/api/automation/competitors/', json={
        'competitor_name': '竞品 A',
        'platform': 'tmall',
        'current_price': 100,
        'rank': 8,
    }, headers=_headers(seed)).get_json()['data']

    scanned = client.post(
        f'/api/automation/competitors/{created["id"]}/scan/',
        json={'current_price': 88, 'rank': 2, 'activity': '满减'},
        headers=_headers(seed),
    ).get_json()

    assert scanned['status'] == 200
    assert '降价超过5%' in scanned['data']['alert_flags']
    assert '进入前三' in scanned['data']['alert_flags']


def test_creative_generation_and_inspection(api):
    client, seed = api['client'], api['seed']
    generated = client.post('/api/automation/creative/generate/', json={
        'product_id': seed['product_a'].id,
        'channel': '淘宝',
    }, headers=_headers(seed)).get_json()
    assert generated['status'] == 200
    assert generated['data']['channel'] == '淘宝'
    assert len(generated['data']['size_plan']) == 3

    inspected = client.post('/api/automation/creative/inspect/', json={
        'has_image': True,
        'width': 1200,
        'height': 628,
        'target_width': 800,
        'target_height': 800,
    }, headers=_headers(seed)).get_json()
    assert inspected['status'] == 200
    assert inspected['data']['passed'] is False
    assert inspected['data']['output']['mode'] == 'center_crop'


def test_generated_creative_image_can_be_saved_and_published(api, tmp_path):
    client, seed = api['client'], api['seed']
    # 1x1 PNG：验证 Base64 结果会落到租户目录，而不是把临时外链写进商品。
    pixel = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII='
    app = client.application
    app.config['UPLOAD_FOLDER'] = str(tmp_path)
    response = client.post('/api/automation/creative/apply/', json={
        'product_id': seed['product_a'].id,
        'image': {'b64_json': pixel, 'model': 'test-image'},
        'publish': True,
    }, headers=_headers(seed))
    body = response.get_json()

    assert body['status'] == 200
    assert body['data']['published'] is True
    assert body['data']['path'].startswith(f"/static/upload/{seed['id_a']}/")
    assert (tmp_path / str(seed['id_a'])).exists()
    with app.app_context():
        with tenant_context(disabled=True):
            product = models.Product.query.get(seed['product_a'].id)
            assert product.state == 2
            assert product.big_img == body['data']['path']
            assert product.small_img == body['data']['path']


def test_generated_image_url_is_never_fetched(api, monkeypatch):
    import urllib.request

    def unexpected_network_request(*args, **kwargs):
        raise AssertionError('image URLs must not trigger server-side requests')

    monkeypatch.setattr(urllib.request, 'urlopen', unexpected_network_request)
    response = api['client'].post('/api/automation/creative/apply/', json={
        'product_id': api['seed']['product_a'].id,
        'image': {'url': 'http://127.0.0.1/private'},
    }, headers=_headers(api['seed'])).get_json()
    assert response['status'] == 400
    assert 'Base64' in response['msg']


def test_creative_generation_requests_and_returns_base64(api, monkeypatch):
    formats = []

    def generate_image(*args, **kwargs):
        formats.append(kwargs.get('response_format'))
        return {'ok': True, 'model': 'test-image', 'b64_json': 'encoded-image'}

    monkeypatch.setattr('flask_shop.agents.tools.agnes_client.generate_image', generate_image)
    result = api['client'].post('/api/automation/creative/generate/', json={
        'product_id': api['seed']['product_a'].id, 'generate_image': True,
    }, headers=_headers(api['seed'])).get_json()
    assert result['status'] == 200
    assert formats == ['b64_json']
    assert result['data']['image']['b64_json'] == 'encoded-image'


def test_creative_auto_start_runs_to_completion(api, tmp_path, monkeypatch):
    client, seed = api['client'], api['seed']
    app = client.application
    _enable_demo_tenant(app, seed['id_a'])
    app.config['UPLOAD_FOLDER'] = str(tmp_path)
    pixel = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII='

    def fake_content(tenant_id, draft, *, use_llm=True):
        return {'status': 200, 'data': {'description': '自动生成的商品简介', 'sell_points': '真实卖点; 信息透明'}}

    monkeypatch.setattr('flask_shop.agents.content_agent.run_product_content_agent', fake_content)
    monkeypatch.setattr(
        'flask_shop.agents.tools.agnes_client.generate_image',
        lambda *args, **kwargs: {'ok': True, 'model': 'test-image', 'b64_json': pixel},
    )
    started = client.post('/api/automation/creative/auto/start/', json={
        'scope': 'missing_image', 'publish': True,
    }, headers=_headers(seed)).get_json()
    assert started['status'] == 202, started
    run_id = started['data']['id']

    status = None
    for _ in range(30):
        status = client.get(f'/api/automation/creative/auto/{run_id}/', headers=_headers(seed)).get_json()
        if status['data']['status'] not in {'running', 'stopping'}:
            break
        time.sleep(0.05)
    assert status['data']['status'] == 'success'
    assert status['data']['output']['succeeded'] == 1
    restored = client.get('/api/automation/creative/auto/current/', headers=_headers(seed)).get_json()
    assert restored['status'] == 200
    assert restored['data']['id'] == run_id
    assert restored['data']['status'] == 'success'
    with app.app_context():
        with tenant_context(disabled=True):
            product = models.Product.query.get(seed['product_a'].id)
            assert product.state == 2
            assert product.big_img.startswith(f"/static/upload/{seed['id_a']}/")


def test_creative_auto_audit_rollback_does_not_undo_success(api, tmp_path, monkeypatch):
    client, seed = api['client'], api['seed']
    app = client.application
    _enable_demo_tenant(app, seed['id_a'])
    app.config['UPLOAD_FOLDER'] = str(tmp_path)
    pixel = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII='
    audit_calls = []

    def failed_audit(action, *args, **kwargs):
        if action == 'automation.creative_auto_item':
            audit_calls.append(action)
            db.session.rollback()
            return False
        return True

    monkeypatch.setattr('flask_shop.automation.views.write_audit', failed_audit)
    monkeypatch.setattr(
        'flask_shop.agents.content_agent.run_product_content_agent',
        lambda *args, **kwargs: {'data': {'description': '测试简介'}},
    )
    monkeypatch.setattr(
        'flask_shop.agents.tools.agnes_client.generate_image',
        lambda *args, **kwargs: {'ok': True, 'model': 'test-image', 'b64_json': pixel},
    )
    started = client.post('/api/automation/creative/auto/start/', json={
        'scope': 'missing_image', 'publish': True,
    }, headers=_headers(seed)).get_json()
    assert started['status'] == 202
    run_id = started['data']['id']
    for _ in range(30):
        status = client.get(f'/api/automation/creative/auto/{run_id}/', headers=_headers(seed)).get_json()
        if status['data']['status'] not in {'running', 'stopping'}:
            break
        time.sleep(0.05)
    assert status['data']['status'] == 'success'
    assert status['data']['output']['succeeded'] == 1
    assert audit_calls == ['automation.creative_auto_item']
    with app.app_context(), tenant_context(disabled=True):
        product = db.session.get(models.Product, seed['product_a'].id)
        assert product.state == 2
        assert product.big_img.startswith(f"/static/upload/{seed['id_a']}/")


def test_creative_auto_can_create_new_demo_product(api, tmp_path, monkeypatch):
    client, seed = api['client'], api['seed']
    app = client.application
    app.config['UPLOAD_FOLDER'] = str(tmp_path)
    _enable_demo_tenant(app, seed['id_a'])
    pixel = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII='
    monkeypatch.setattr(
        'flask_shop.agents.tools.llm_client.chat_completions',
        lambda *args, **kwargs: {'ok': True, 'content': '[{"name":"自动演示收纳盒","price":66,"stock":30,"description":"演示商品简介","sell_points":"分区收纳；轻便易用"}]'},
    )
    monkeypatch.setattr(
        'flask_shop.agents.content_agent.run_product_content_agent',
        lambda *args, **kwargs: {'status': 200, 'data': {'description': '演示商品简介', 'sell_points': '分区收纳；轻便易用'}},
    )
    monkeypatch.setattr(
        'flask_shop.agents.tools.agnes_client.generate_image',
        lambda *args, **kwargs: {'ok': True, 'model': 'test-image', 'b64_json': pixel},
    )
    started = client.post('/api/automation/creative/auto/start/', json={
        'scope': 'create_new', 'count': 1, 'publish': True,
    }, headers=_headers(seed)).get_json()
    assert started['status'] == 202, started
    run_id = started['data']['id']
    status = None
    for _ in range(30):
        status = client.get(f'/api/automation/creative/auto/{run_id}/', headers=_headers(seed)).get_json()
        if status['data']['status'] not in {'running', 'stopping'}:
            break
        time.sleep(0.05)
    assert status['data']['status'] == 'success'
    with app.app_context():
        with tenant_context(disabled=True):
            created = models.Product.query.filter_by(tenant_id=seed['id_a'], name='自动演示收纳盒').first()
            assert created is not None
            assert created.state == 2
            assert created.big_img.startswith(f"/static/upload/{seed['id_a']}/")
