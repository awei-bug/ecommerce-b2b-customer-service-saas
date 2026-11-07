import pytest

from flask_shop import db, models
from flask_shop.utils import hub_auto_sync, hub_client
from flask_shop.utils.tenant_query import tenant_context


def configure(app):
    app.config.update(DATA_HUB_URL='http://hub', DATA_HUB_TOKEN='test-token', DATA_HUB_TENANT_SLUG='test-a')
    tenant = db.session.get(models.Tenant, app._seed_ctx['id_a'])
    tenant.data_mode = 'demo'
    db.session.commit()
    assert (tenant.slug, tenant.data_mode, tenant.status) == ('test-a', 'demo', 1)
    return tenant


def test_auto_sync_draft_repeat_preserves_business_fields_and_no_ack(app, monkeypatch):
    item = {'tenant_slug': 'test-a', 'external_id': 'auto-1', 'title': '自动同步商品', 'price': 25, 'stock': 7, 'status': 'draft', 'selling_points': ['轻便']}
    with app.app_context():
        tenant = configure(app)
        monkeypatch.setattr(hub_client, 'fetch_products', lambda **kwargs: [item])
        monkeypatch.setattr(hub_client, 'ack', lambda *args: pytest.fail('automatic sync must not acknowledge'))
        result = hub_auto_sync.run_once()
        assert result['created'] == 1
        with tenant_context(tenant_id=tenant.id):
            knowledge = models.ProductKnowledge.query.filter_by(external_id='auto-1').one()
            product = db.session.get(models.Product, knowledge.product_id)
            assert product.state == 0 and product.number == 7
            product.state = 2
            product.price = 99
            product.number = 3
            product.name = '商家修改名称'
            db.session.commit()
        item.update(title='远端修改名称', price=12, stock=99, selling_points=['更新卖点'])
        assert hub_auto_sync.run_once()['updated'] == 1
        with tenant_context(tenant_id=tenant.id):
            assert (product.name, float(product.price), product.number, product.state) == ('商家修改名称', 99, 3, 2)
            assert knowledge.knowledge()['selling_points'] == ['更新卖点']
            assert knowledge.status == 'published'
            assert models.ProductKnowledge.query.filter_by(external_id='auto-1').count() == 1


def test_auto_sync_rejects_live_tenant_and_missing_auth(app, monkeypatch):
    with app.app_context():
        tenant = configure(app)
        tenant.data_mode = 'live'
        db.session.commit()
        monkeypatch.setattr(hub_client, 'fetch_products', lambda **kwargs: pytest.fail('must not fetch'))
        with pytest.raises(ValueError, match='演示租户'):
            hub_auto_sync.run_once()
        tenant.data_mode = 'demo'
        app.config['DATA_HUB_TOKEN'] = ''
        with pytest.raises(ValueError, match='令牌'):
            hub_auto_sync.run_once()


def test_auto_sync_pages_and_skips_archived(app, monkeypatch):
    with app.app_context():
        configure(app)
        monkeypatch.setattr(hub_auto_sync, 'PAGE_SIZE', 2)
        pages = {0: [{'tenant_slug': 'test-a', 'external_id': 'archived', 'title': '归档', 'price': 10, 'status': 'archived'}, {'tenant_slug': 'test-a', 'external_id': 'first', 'title': '第一页', 'price': 10}], 2: [{'tenant_slug': 'test-a', 'external_id': 'second', 'title': '第二页', 'price': 20}]}
        monkeypatch.setattr(hub_client, 'fetch_products', lambda **kwargs: pages.get(kwargs.get('offset', 0), []))
        result = hub_auto_sync.run_once()
        assert result['received'] == 3 and result['created'] == 2
        with tenant_context(tenant_id=app._seed_ctx['id_a']):
            assert models.ProductKnowledge.query.filter_by(external_id='archived').first() is None
            assert models.ProductKnowledge.query.filter_by(external_id='second').first() is not None


def test_auto_sync_failure_keeps_existing_product(app, monkeypatch):
    with app.app_context():
        configure(app)
        def fail(**kwargs):
            raise hub_client.HubError('unavailable')
        monkeypatch.setattr(hub_client, 'fetch_products', fail)
        with pytest.raises(hub_client.HubError):
            hub_auto_sync.run_once()
        assert app._seed_ctx['product_a'].name == 'A-唯一商品-xyz'
        monkeypatch.setattr(hub_client, 'fetch_products', lambda **kwargs: [{'tenant_slug': 'test-a', 'external_id': 'recovered', 'title': '恢复商品', 'price': 10}])
        assert hub_auto_sync.run_once()['created'] == 1


def test_auto_sync_rejects_cross_tenant_response(app, monkeypatch):
    with app.app_context():
        configure(app)
        monkeypatch.setattr(hub_client, 'fetch_products', lambda **kwargs: [{'tenant_slug': 'test-b', 'external_id': 'foreign', 'title': '其他店', 'price': 10}])
        with pytest.raises(hub_client.HubError, match='租户不匹配'):
            hub_auto_sync.run_once()
        with tenant_context(tenant_id=app._seed_ctx['id_a']):
            assert models.ProductKnowledge.query.filter_by(external_id='foreign').first() is None


def test_name_conflict_is_reported_and_later_cycle_recovers(app, monkeypatch):
    with app.app_context():
        tenant = configure(app)
        item = {'tenant_slug': 'test-a', 'external_id': 'conflict-id', 'title': 'A-唯一商品-xyz', 'price': 10}
        monkeypatch.setattr(hub_client, 'fetch_products', lambda **kwargs: [item])
        failed = hub_auto_sync.run_once()
        assert failed['errors'] == 1
        assert failed['issues'] == [{'id': 'conflict-id', 'code': 'name_conflict'}]
        with tenant_context(tenant_id=tenant.id):
            original = db.session.get(models.Product, app._seed_ctx['product_a'].id)
            original.name = '已核对的原商品'
            db.session.commit()
        recovered = hub_auto_sync.run_once()
        assert recovered['created'] == 1 and recovered['errors'] == 0
        with tenant_context(tenant_id=tenant.id):
            knowledge = models.ProductKnowledge.query.filter_by(external_id='conflict-id').one()
            assert db.session.get(models.Product, knowledge.product_id).state == 0
