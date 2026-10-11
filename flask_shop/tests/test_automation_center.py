from datetime import date
import time

from flask_shop import db, models
from flask_shop.utils.tenant_query import tenant_context


def _headers(seed, key='token_a'):
    return {'token': seed[key]}


def test_automation_overview_bootstraps_eight_modules(api):
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


def test_campaign_data_is_tenant_isolated_and_drives_roas(api):
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


def test_rule_run_writes_observable_log(api):
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


def test_competitor_scan_detects_price_drop(api):
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


def test_creative_auto_start_runs_to_completion(api, tmp_path, monkeypatch):
    client, seed = api['client'], api['seed']
    app = client.application
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


def test_creative_auto_can_create_new_demo_product(api, tmp_path, monkeypatch):
    client, seed = api['client'], api['seed']
    app = client.application
    app.config['UPLOAD_FOLDER'] = str(tmp_path)
    with app.app_context():
        with tenant_context(disabled=True):
            models.Tenant.query.get(seed['id_a']).data_mode = 'demo'
            db.session.commit()
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
