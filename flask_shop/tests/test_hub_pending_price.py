import pytest

from flask_shop import db, models
from flask_shop.utils import hub_auto_sync, hub_client, hub_sync
from flask_shop.utils.tenant_query import tenant_context
from flask_shop.utils.token import generate_token


def prepare(app, item):
    app.config.update(DATA_HUB_URL='http://hub', DATA_HUB_TOKEN='test-token', DATA_HUB_TENANT_SLUG='test-a')
    tenant = db.session.get(models.Tenant, app._seed_ctx['id_a'])
    tenant.data_mode = 'demo'
    db.session.commit()
    result = hub_sync._apply_item(tenant.id, item, publish=False, safe_existing=True)
    assert result['action'] == 'pending'
    db.session.commit()
    with tenant_context(tenant_id=tenant.id):
        return models.ProductKnowledge.query.filter_by(external_id=item['external_id']).one().id


def test_pending_price_creates_draft_once_and_auto_sync_preserves_local_price(app, api, monkeypatch):
    item = {'tenant_slug': 'test-a', 'external_id': 'pending-1', 'title': '待补价水杯', 'price': None, 'stock': 7, 'selling_points': ['轻便']}
    with app.app_context():
        knowledge_id = prepare(app, item)
        url = f'/products/hub/pending/{knowledge_id}/price/'
        headers = {'token': api['seed']['token_a']}
        response = api['client'].post(url, headers=headers, json={'price': '129.50'}).get_json()
        assert response['status'] == 200
        product_id = response['data']['product_id']
        with tenant_context(tenant_id=app._seed_ctx['id_a']):
            product = db.session.get(models.Product, product_id)
            db.session.refresh(product)
            assert product.state == 0 and float(product.price) == 129.50 and product.number == 7
        assert api['client'].post(url, headers=headers, json={'price': '10'}).get_json()['status'] == 409
        monkeypatch.setattr(hub_client, 'fetch_products', lambda **kwargs: [item])
        assert hub_auto_sync.run_once()['updated'] == 1
        with tenant_context(tenant_id=app._seed_ctx['id_a']):
            db.session.refresh(product)
            assert float(product.price) == 129.50 and product.state == 0
            assert models.ProductKnowledge.query.filter_by(external_id='pending-1').one().product_id == product_id


@pytest.mark.parametrize('price', [0, -1, 'NaN', 'Infinity', '1.001', '10000000000', True, 'abc'])
def test_invalid_price_rejected(app, api, price):
    with app.app_context():
        knowledge_id = prepare(app, {'external_id': 'pending-1', 'title': '待补价水杯', 'price': None})
        response = api['client'].post(f'/products/hub/pending/{knowledge_id}/price/', headers={'token': api['seed']['token_a']}, json={'price': price}).get_json()
        assert response['status'] == 400


def test_pending_price_denies_other_tenant_and_name_collision(app, api):
    with app.app_context():
        knowledge_id = prepare(app, {'external_id': 'collision', 'title': app._seed_ctx['product_a'].name, 'price': None})
        url = f'/products/hub/pending/{knowledge_id}/price/'
        assert api['client'].post(url, headers={'token': api['seed']['token_b']}, json={'price': '10'}).get_json()['status'] == 403
        result = api['client'].post(url, headers={'token': api['seed']['token_a']}, json={'price': '10'}).get_json()
        assert result['status'] == 409 and '同名' in result['msg']
        with tenant_context(tenant_id=app._seed_ctx['id_a']):
            assert models.ProductKnowledge.query.filter_by(id=knowledge_id).one().product_id is None


def test_pending_price_requires_write_permission(app, api):
    with app.app_context():
        knowledge_id = prepare(app, {'external_id': 'pending', 'title': '只读商品', 'price': None})
        tenant_id = app._seed_ctx['id_a']
        with tenant_context(tenant_id=tenant_id):
            role = models.Role(tenant_id=tenant_id, name='只读员工', perm_codes='["product:read"]')
            db.session.add(role)
            db.session.flush()
            user = models.User(tenant_id=tenant_id, name='readonly_price', role_id=role.id)
            user.password = 'test-pass'
            db.session.add(user)
            db.session.commit()
            token = generate_token({'typ': 'merchant', 'staff_id': user.id, 'tenant_id': tenant_id})
        response = api['client'].post(f'/products/hub/pending/{knowledge_id}/price/', headers={'token': token}, json={'price': '10'}).get_json()
        assert response['status'] == 403
