import pytest

from flask_shop import models
from flask_shop.utils import hub_client, hub_publish


def test_publish_binds_external_id_and_reuses_it(app, monkeypatch, tenant_a_context):
    with app.app_context():
        tenant = app._seed_ctx['ta']
        product = app._seed_ctx['product_a']
        ingested = []

        def fake_ingest(items, source='shop_publish', job_id=''):
            ingested.extend(items)
            return {
                'ok': True,
                'results': [{
                    'external_id': items[0]['external_id'],
                    'ok': True,
                    'action': 'created',
                    'version': 1,
                }],
            }

        monkeypatch.setattr(hub_client, 'ingest', fake_ingest)
        monkeypatch.setattr(hub_client, 'fetch_product', lambda external_id: {
            'external_id': external_id,
            'title': product.name,
            'price': 20.0,
            'stock': product.number,
            'selling_points': ['原卖点'],
            'ops_note': '【运营提示】仅剩 3 件',
            'version': 1,
        })

        first = hub_publish.publish_product(tenant, product.id)
        assert first['external_id'] == f'yg-{tenant.id}-{product.id}'
        assert first['action'] == 'created'
        assert first['reused_binding'] is False
        assert ingested[0]['title'] == product.name
        assert ingested[0]['selling_points'] == hub_publish._split_points(product.sell_points)
        # 反复上行不得把内容平台生成的运营提示清空。
        assert ingested[0]['ops_note'] == '【运营提示】仅剩 3 件'

        binding = models.ProductKnowledge.query.filter_by(
            tenant_id=tenant.id, external_id=first['external_id']
        ).first()
        assert binding is not None
        assert binding.product_id == product.id

        again = hub_publish.publish_product(tenant, product.id)
        assert again['external_id'] == first['external_id']
        assert again['reused_binding'] is True
        assert models.ProductKnowledge.query.filter_by(
            tenant_id=tenant.id, product_id=product.id
        ).count() == 1


def test_publish_does_not_write_binding_when_hub_rejects(app, monkeypatch, tenant_a_context):
    with app.app_context():
        tenant = app._seed_ctx['ta']
        product = app._seed_ctx['product_a']
        monkeypatch.setattr(
            hub_client, 'ingest',
            lambda *args, **kwargs: {'ok': False, 'results': [{'ok': False, 'message': '缺少商品名称'}]},
        )
        monkeypatch.setattr(hub_client, 'fetch_product', lambda external_id: {})

        with pytest.raises(hub_publish.PublishError):
            hub_publish.publish_product(tenant, product.id)

        assert models.ProductKnowledge.query.filter_by(product_id=product.id).first() is None


class _LegacyProduct:
    """早期版本留下的脏数据：顾客可见字段里混入了运营提示。"""
    id = 1
    name = '演示商品'
    price = 129.0
    number = 3
    introduce = '便携式榨汁杯，380ml 容量。 【运营提示】仅剩 2 件，建议改为预约口径'
    sell_points = '容量大；库存提示：当前仅剩 2 件'
    big_img = ''
    small_img = ''


def test_build_item_strips_legacy_ops_text_from_customer_fields():
    item = hub_publish.build_item(
        _LegacyProduct(), 'yg-1-1', {'ops_note': '【运营提示】仅剩 2 件'}
    )

    assert item['desc_zh'] == '便携式榨汁杯，380ml 容量。'
    assert item['selling_points'] == ['容量大']
    assert item['ops_note'] == '【运营提示】仅剩 2 件', '现有提示必须原样带回'


def test_publish_rejects_unknown_product(app, monkeypatch):
    with app.app_context():
        tenant = app._seed_ctx['ta']
        monkeypatch.setattr(hub_client, 'ingest', lambda *args, **kwargs: {'ok': True, 'results': []})

        with pytest.raises(hub_publish.PublishError):
            hub_publish.publish_product(tenant, 10 ** 8)
