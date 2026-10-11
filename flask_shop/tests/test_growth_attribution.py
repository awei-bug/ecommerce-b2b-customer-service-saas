from flask_shop import db, models
from flask_shop.utils import growth_webhook
from flask_shop.utils.tenant_query import tenant_context
from flask_shop.utils.token import generate_customer_token


def test_attribution_is_carried_from_tracking_session_to_order(api, app, monkeypatch):
    emitted = []
    monkeypatch.setattr(
        growth_webhook, 'emit_landing_view_conversion',
        lambda attribution, tenant_id, request_path=None: emitted.append(
            ('landing.view', dict(attribution), tenant_id, request_path)
        ) or True,
    )
    monkeypatch.setattr(
        growth_webhook, 'emit_order_created_conversion',
        lambda order: emitted.append(('order.created', order.id, order.campaign_id)) or True,
    )
    client, seed = api['client'], api['seed']
    with app.app_context(), tenant_context(disabled=True):
        seed['ta'].pay_qr_wechat = '/static/pay-qr.png'
        customer = models.Customer(
            tenant_id=seed['ta'].id,
            phone='13900003333',
            nickname='growth-buyer',
            status=1,
        )
        product = models.Product(
            tenant_id=seed['ta'].id,
            name='增长归因测试商品',
            price=19.9,
            number=10,
        )
        db.session.add_all([customer, product])
        db.session.commit()
        knowledge = models.ProductKnowledge(
            tenant_id=seed['ta'].id,
            product_id=product.id,
            external_id='p-growth-test',
            title=product.name,
        )
        db.session.add(knowledge)
        db.session.commit()
        token = generate_customer_token(customer)
        product_id = product.id

    tenant_headers = {'X-Tenant-Slug': 'test-a'}
    tracked = client.get(
        f'/api/c/attribution/track/?campaign_id=campaign_demo&content_id=video_001'
        f'&product_id={product_id}&source=tiktok&medium=short_video',
        headers=tenant_headers,
    )
    assert tracked.status_code == 200
    tracked_body = tracked.get_json()
    assert tracked_body['data']['source'] == 'tiktok'
    assert tracked_body['data']['product_id'] == str(product_id)
    assert tracked_body['data']['visitor_id'].startswith('visitor_')
    assert tracked_body['tracked'] is True
    assert tracked_body['idempotent'] is False
    assert emitted[0][0] == 'landing.view'
    assert emitted[0][1]['campaign_id'] == 'campaign_demo'
    assert emitted[0][3] == '/api/c/attribution/track/'

    duplicate = client.get(
        f'/api/c/attribution/track/?campaign_id=campaign_demo&content_id=video_001'
        f'&product_id={product_id}&source=tiktok&medium=short_video',
        headers=tenant_headers,
    )
    assert duplicate.status_code == 200
    assert duplicate.get_json()['idempotent'] is True
    assert len(emitted) == 1

    created = client.post(
        '/api/c/orders/',
        json={
            'items': [{'pid': product_id, 'number': 1}],
            'address': '归因测试地址',
            'consultation_session_id': 'support-session-001',
        },
        headers={'token': token, **tenant_headers},
    )
    body = created.get_json()
    assert created.status_code == 200, body
    assert body['data']['campaign_id'] == 'campaign_demo'
    assert body['data']['content_id'] == 'video_001'
    assert body['data']['attribution_source'] == 'tiktok'
    assert body['data']['attribution_medium'] == 'short_video'
    assert body['data']['consultation_session_id'] == 'support-session-001'
    assert emitted[1] == ('order.created', body['data']['id'], 'campaign_demo')
