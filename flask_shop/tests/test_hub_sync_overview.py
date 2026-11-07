import json

from flask_shop import db, models
from flask_shop.utils import hub_auto_sync
from flask_shop.utils.tenant_query import tenant_context
from flask_shop.utils.token import generate_token


def test_overview_is_tenant_scoped_and_shows_actual_product_state(app, api):
    with app.app_context():
        app.config.update(DATA_HUB_URL='http://hub', DATA_HUB_TENANT_SLUG='test-a')
        tenant = db.session.get(models.Tenant, app._seed_ctx['id_a'])
        tenant.data_mode = 'demo'
        with tenant_context(tenant_id=tenant.id):
            db.session.add(models.ProductKnowledge(tenant_id=tenant.id, external_id='draft-id', product_id=app._seed_ctx['product_a'].id, title='草稿知识', status='published'))
            db.session.add(models.ProductKnowledge(tenant_id=tenant.id, external_id='pending-id', title='待补价', status='pending_price'))
            product = db.session.get(models.Product, app._seed_ctx['product_a'].id)
            product.state = 0
            db.session.add(models.AuditLog(tenant_id=tenant.id, action='product.hub_auto_sync', detail=json.dumps({'status': 'partial', 'created': 1, 'updated': 0, 'pending': 1, 'errors': 1})))
            db.session.commit()
        other_id = app._seed_ctx['id_b']
        with tenant_context(tenant_id=other_id):
            db.session.add(models.ProductKnowledge(tenant_id=other_id, external_id='foreign-id', title='其他店商品', status='draft'))
            db.session.commit()
        response = api['client'].get('/products/hub/overview/', headers={'token': api['seed']['token_a']}).get_json()
        assert response['status'] == 200
        data = response['data']
        assert data['last_cycle']['status'] == 'partial' and data['last_cycle']['errors'] == 1
        states = {row['external_id']: row['state'] for row in data['items']}
        assert states == {'draft-id': 'draft', 'pending-id': 'pending_price'}
        other = api['client'].get('/products/hub/overview/', headers={'token': api['seed']['token_b']}).get_json()
        assert other['data'] == {'available': False}
        assert api['client'].post('/products/hub/sync/', headers={'token': api['seed']['token_b']}, json={}).get_json()['status'] == 403


def test_overview_requires_product_write(app, api):
    with app.app_context():
        tenant_id = app._seed_ctx['id_a']
        with tenant_context(tenant_id=tenant_id):
            role = models.Role(tenant_id=tenant_id, name='只读员工', perm_codes='["product:read"]')
            db.session.add(role)
            db.session.flush()
            user = models.User(tenant_id=tenant_id, name='readonly', role_id=role.id)
            user.password = 'test-pass'
            db.session.add(user)
            db.session.commit()
            token = generate_token({'typ': 'merchant', 'staff_id': user.id, 'tenant_id': tenant_id})
        response = api['client'].get('/products/hub/overview/', headers={'token': token}).get_json()
        assert response['status'] == 403


def test_cycle_record_reports_failure_and_does_not_leak_exception(app, monkeypatch):
    with app.app_context():
        tenant = db.session.get(models.Tenant, app._seed_ctx['id_a'])
        tenant.data_mode = 'demo'
        db.session.commit()
        app.config['DATA_HUB_TENANT_SLUG'] = 'test-a'
        captured = []
        monkeypatch.setattr(hub_auto_sync, 'write_audit', lambda *args, **kwargs: captured.append((args, kwargs)) or True)
        assert hub_auto_sync.record_cycle(failed=True)
        args, kwargs = captured[0]
        assert json.loads(args[3])['status'] == 'failed'
        assert kwargs['tenant_id'] == tenant.id and kwargs['actor_type'] == 'system'


def test_issue_records_are_bounded_and_never_expose_raw_error(app, api, monkeypatch):
    with app.app_context():
        tenant = db.session.get(models.Tenant, app._seed_ctx['id_a'])
        tenant.data_mode = 'demo'
        db.session.commit()
        app.config.update(DATA_HUB_TENANT_SLUG='test-a', DATA_HUB_URL='http://hub')
        captured = []
        monkeypatch.setattr(hub_auto_sync, 'write_audit', lambda *args, **kwargs: captured.append(args[3]) or True)
        assert hub_auto_sync.record_cycle({'errors': 4, 'issues': [{'id': 'a' * 128, 'code': 'name_conflict'}, {'id': 'b' * 128, 'code': 'processing_error'}, {'id': 'c' * 128, 'code': 'unknown-secret'}]})
        detail = captured[0]
        parsed = json.loads(detail)
        assert len(detail) <= 512 and parsed['issues_truncated'] is True
        assert 'unknown-secret' not in detail
        with tenant_context(tenant_id=tenant.id):
            db.session.add(models.AuditLog(tenant_id=tenant.id, action='product.hub_auto_sync', detail=detail))
            db.session.commit()
        response = api['client'].get('/products/hub/overview/', headers={'token': api['seed']['token_a']}).get_json()
        cycle = response['data']['last_cycle']
        assert cycle['issues'][0]['external_id'] == 'a' * 128
        assert '同名' in cycle['issues'][0]['message']
        assert cycle['issues_truncated'] is True
        assert 'unknown-secret' not in json.dumps(cycle)
