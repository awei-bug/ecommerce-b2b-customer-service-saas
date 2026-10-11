from flask_shop import models
from flask_shop.utils import growth_webhook
from flask_shop.utils.tenant_query import tenant_context


def test_public_lead_is_persisted_scored_and_attributed(api, app, monkeypatch):
    emitted = []
    monkeypatch.setattr(
        growth_webhook,
        'emit_landing_view_conversion',
        lambda attribution, tenant_id, request_path=None: True,
    )
    monkeypatch.setattr(
        growth_webhook,
        'emit_lead_created_conversion',
        lambda lead: emitted.append(lead.to_dict()) or True,
    )
    client, seed = api['client'], api['seed']

    tracked = client.get(
        '/api/c/attribution/track/?campaign_id=campaign_demo&content_id=image_001&source=xiaohongshu&medium=social_image&visitor_id=visitor-003',
        headers={'X-Tenant-Slug': 'test-a'},
    )
    assert tracked.status_code == 200

    response = client.post(
        '/api/c/leads/',
        headers={'X-Tenant-Slug': 'test-a'},
        json={
            'product_id': seed['product_a'].id,
            'contact_name': '徐先生',
            'contact_type': 'wechat',
            'contact_value': 'wx-growth-demo',
            'demand': '需要 20 件并确认优惠和到货时间',
            'consent': True,
        },
    )
    body = response.get_json()
    assert response.status_code == 201, body
    assert body['data']['campaign_id'] == 'campaign_demo'
    assert body['data']['content_id'] == 'image_001'
    assert body['data']['visitor_id'] == 'visitor-003'
    assert body['data']['score'] == 100
    assert body['data']['temperature'] == 'hot'
    assert emitted[0]['contact_value'] == 'wx-growth-demo'

    with app.app_context(), tenant_context(disabled=True):
        lead = models.GrowthLead.query.one()
        assert lead.tenant_id == seed['id_a']
        assert lead.product_id == seed['product_a'].id


def test_public_lead_rejects_missing_contact_and_foreign_product(api):
    client, seed = api['client'], api['seed']
    missing = client.post('/api/c/leads/', headers={'X-Tenant-Slug': 'test-a'}, json={})
    assert missing.status_code == 400

    foreign = client.post(
        '/api/c/leads/',
        headers={'X-Tenant-Slug': 'test-a'},
        json={'product_id': seed['product_b'].id, 'contact_type': 'phone', 'contact_value': '13900000000'},
    )
    assert foreign.status_code == 404
