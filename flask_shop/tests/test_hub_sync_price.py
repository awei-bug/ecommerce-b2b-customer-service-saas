"""hub 同步的价格权威边界。

售价由商城管理，hub 只在新建商品时提供初始价。重复同步不得覆盖商城改价，
也不得在下单后用内容侧旧价改写交易定价。
"""
from flask_shop import db, models
from flask_shop.utils.hub_sync import _apply_item
from flask_shop.utils.tenant_query import tenant_context


def test_new_product_uses_hub_price(app):
    with app.app_context():
        tenant_id = app._seed_ctx['id_a']
        item = {
            'external_id': 'hub-price',
            'title': '价格同步商品',
            'price': 25,
            'stock': 7,
        }
        result = _apply_item(tenant_id, item, publish=True)
        db.session.flush()
        with tenant_context(tenant_id=tenant_id):
            product = db.session.get(models.Product, result['product_id'])
            assert float(product.price) == 25.0


def test_resync_does_not_overwrite_merchant_price(app):
    with app.app_context():
        tenant_id = app._seed_ctx['id_a']
        item = {
            'external_id': 'hub-price',
            'title': '价格同步商品',
            'price': 25,
            'stock': 7,
        }
        result = _apply_item(tenant_id, item, publish=True)
        db.session.flush()
        with tenant_context(tenant_id=tenant_id):
            product = db.session.get(models.Product, result['product_id'])
            product.price = 39.9
        db.session.flush()

        item['price'] = 18.0
        _apply_item(tenant_id, item, publish=True)
        db.session.flush()
        assert float(product.price) == 39.9
        assert product.name == '价格同步商品'
