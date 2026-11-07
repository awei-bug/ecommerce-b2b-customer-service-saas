from flask_shop import db, models
from flask_shop.utils import hub_sync
from flask_shop.utils.tenant_query import tenant_context


def test_different_external_ids_with_same_name_do_not_merge(app):
    with app.app_context():
        tenant_id = app._seed_ctx['id_a']
        first = {'external_id': 'first', 'title': '同名商品', 'price': 10, 'stock': 2}
        second = {'external_id': 'second', 'title': '同名商品', 'price': 99, 'stock': 9}
        result = hub_sync._apply_item(tenant_id, first, publish=True)
        db.session.flush()
        conflict = hub_sync._apply_item(tenant_id, second, publish=True)
        db.session.flush()

        with tenant_context(tenant_id=tenant_id):
            product = db.session.get(models.Product, result['product_id'])
            assert conflict['action'] == 'error'
            assert float(product.price) == 10
            assert product.number == 2
            assert models.ProductKnowledge.query.filter_by(external_id='second').first() is None


def test_truncated_title_collision_is_rejected(app):
    with app.app_context():
        tenant_id = app._seed_ctx['id_a']
        title = '商' * 128
        hub_sync._apply_item(tenant_id, {'external_id': 'first', 'title': title, 'price': 10}, True)
        db.session.flush()
        conflict = hub_sync._apply_item(
            tenant_id, {'external_id': 'second', 'title': title + '其他', 'price': 20}, True
        )
        assert conflict['action'] == 'error'


def test_cross_tenant_product_link_is_rejected_even_when_cached(app):
    with app.app_context():
        tenant_id = app._seed_ctx['id_a']
        other_product = app._seed_ctx['product_b']
        db.session.add(models.ProductKnowledge(
            tenant_id=tenant_id, external_id='bad-link', product_id=other_product.id,
            title='跨租户错误关联', price=10,
        ))
        db.session.flush()
        result = hub_sync._apply_item(
            tenant_id, {'external_id': 'bad-link', 'title': '跨租户错误关联', 'price': 99}, True
        )
        db.session.flush()
        assert result['action'] == 'error'
        assert other_product.name == 'B-唯一商品-xyz'
        assert float(other_product.price) == 20


def test_sync_conflict_is_reported_without_ack(app, monkeypatch):
    with app.app_context():
        tenant = app._seed_ctx['ta']
        item = {'external_id': 'collision', 'title': app._seed_ctx['product_a'].name, 'price': 88}
        acknowledgements = []
        monkeypatch.setattr(hub_sync.hub_client, 'fetch_products', lambda **kwargs: [item])
        monkeypatch.setattr(hub_sync.hub_client, 'ack', lambda *args: acknowledgements.append(args))
        result = hub_sync.sync_from_hub(tenant)

        assert result['summary']['errors'] == 1
        assert result['errors'][0]['external_id'] == 'collision'
        assert acknowledgements == []


def test_existing_identity_updates_and_is_isolated_between_tenants(app):
    with app.app_context():
        first_tenant = app._seed_ctx['id_a']
        second_tenant = app._seed_ctx['id_b']
        item = {'external_id': 'shared-id', 'title': '跨店商品', 'price': 10, 'stock': 2}
        first = hub_sync._apply_item(first_tenant, item, publish=True)
        db.session.flush()
        second = hub_sync._apply_item(second_tenant, item, publish=True)
        db.session.flush()

        item['title'] = '更新后的商品'
        item['price'] = 12
        updated = hub_sync._apply_item(first_tenant, item, publish=True)
        db.session.flush()

        assert first['product_id'] != second['product_id']
        assert updated['action'] == 'updated'
        assert updated['product_id'] == first['product_id']
        with tenant_context(tenant_id=second_tenant):
            product = db.session.get(models.Product, second['product_id'])
            assert product.name == '跨店商品'
            assert float(product.price) == 10
