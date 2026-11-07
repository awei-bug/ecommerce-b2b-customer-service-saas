import pytest

from flask_shop import db, models
from flask_shop.utils.hub_sync import _apply_item
from flask_shop.utils.tenant_query import tenant_context


@pytest.mark.parametrize('stock, expected', [(None, 0), (0, 0), (7, 7)])
def test_new_hub_product_does_not_invent_stock(app, stock, expected):
    with app.app_context():
        tenant_id = app._seed_ctx['id_a']
        item = {'external_id': 'hub-stock', 'title': '同步库存商品', 'price': 25}
        if stock is not None:
            item['stock'] = stock

        result = _apply_item(tenant_id, item, publish=True)
        db.session.flush()
        with tenant_context(tenant_id=tenant_id):
            product = db.session.get(models.Product, result['product_id'])
            assert product.number == expected


def test_missing_stock_preserves_existing_product_stock(app):
    with app.app_context():
        tenant_id = app._seed_ctx['id_a']
        item = {'external_id': 'hub-stock', 'title': '同步库存商品', 'price': 25, 'stock': 7}
        result = _apply_item(tenant_id, item, publish=True)
        db.session.flush()
        with tenant_context(tenant_id=tenant_id):
            product = db.session.get(models.Product, result['product_id'])
            product.number = 3
        db.session.flush()

        del item['stock']
        _apply_item(tenant_id, item, publish=True)
        db.session.flush()
        assert product.number == 3


def test_resync_does_not_restore_stock_after_order(api, app):
    tenant_id = api['seed']['id_a']
    item = {'external_id': 'ordered-product', 'title': '下单同步商品', 'price': 25, 'stock': 7}
    with app.app_context():
        result = _apply_item(tenant_id, item, publish=True)
        db.session.commit()
        product_id = result['product_id']

    response = api['client'].post(
        '/orders/',
        json={'items': [{'pid': product_id, 'number': 2}], 'address': '测试地址'},
        headers={'token': api['seed']['token_a']},
    ).get_json()
    assert response['status'] == 200, response

    with app.app_context():
        result = _apply_item(tenant_id, item, publish=True)
        db.session.commit()
        with tenant_context(tenant_id=tenant_id):
            product = db.session.get(models.Product, product_id)
            assert result['action'] == 'updated'
            assert product.number == 5


def test_resync_preserves_sku_and_aggregate_stock(app):
    with app.app_context():
        tenant_id = app._seed_ctx['id_a']
        item = {'external_id': 'sku-product', 'title': '多规格同步商品', 'price': 25, 'stock': 7}
        result = _apply_item(tenant_id, item, publish=True)
        db.session.flush()
        product = db.session.get(models.Product, result['product_id'])
        product.number = 3
        sku = models.ProductSku(tenant_id=tenant_id, product_id=product.id, stock=3, status=1)
        db.session.add(sku)
        db.session.flush()

        _apply_item(tenant_id, item, publish=True)
        db.session.flush()
        assert sku.stock == 3
        assert product.number == 3


def test_first_sync_matching_existing_product_does_not_change_stock(app):
    with app.app_context():
        tenant_id = app._seed_ctx['id_a']
        product_id = app._seed_ctx['product_a'].id
        with tenant_context(tenant_id=tenant_id):
            product = db.session.get(models.Product, product_id)
            product.number = 4
        db.session.flush()

        item = {'external_id': 'existing-product', 'title': product.name, 'price': 25, 'stock': 20}
        result = _apply_item(tenant_id, item, publish=True)
        db.session.flush()

        assert result['action'] == 'error'
        assert product.number == 4
