import json
from datetime import datetime, timezone
from types import SimpleNamespace

from flask_shop.utils import growth_webhook


def test_emit_order_paid_conversion_sends_attribution_payload(monkeypatch):
    captured = {}

    class Response:
        status = 204

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    def fake_urlopen(request, timeout):
        captured['request'] = request
        captured['timeout'] = timeout
        return Response()

    monkeypatch.setenv('CONTENT_PLATFORM_CONVERSION_WEBHOOK', 'http://127.0.0.1:3100/api/integrations/ecommerce/conversions')
    monkeypatch.setenv('CONTENT_PLATFORM_WEBHOOK_TOKEN', 'test-token')
    monkeypatch.setenv('SHOP_CURRENCY', 'CNY')
    monkeypatch.setattr(growth_webhook, 'urlopen', fake_urlopen)

    order = SimpleNamespace(
        id=9001,
        tenant_id=7,
        order_no='ORD-9001',
        price=99,
        campaign_id='campaign_demo',
        content_id='video_001',
        attribution_source='tiktok',
        attribution_medium='short_video',
    )
    payment = SimpleNamespace(
        id=81,
        transaction_id='txn-81',
        paid_at=datetime(2026, 9, 5, 9, 30, tzinfo=timezone.utc),
    )

    assert growth_webhook.emit_order_paid_conversion(order, payment) is True
    assert captured['timeout'] == 3

    request = captured['request']
    headers = {key.lower(): value for key, value in request.header_items()}
    payload = json.loads(request.data.decode('utf-8'))
    assert request.full_url.endswith('/api/integrations/ecommerce/conversions')
    assert headers['content-type'] == 'application/json'
    assert headers['x-integration-token'] == 'test-token'
    assert payload == {
        'eventType': 'order.paid',
        'campaignId': 'campaign_demo',
        'contentId': 'video_001',
        'source': 'tiktok',
        'externalTenantId': '7',
        'externalOrderId': '9001',
        'amount': 99.0,
        'currency': 'CNY',
        'occurredAt': '2026-09-05T09:30:00+00:00',
        'payload': {
            'orderNo': 'ORD-9001',
            'paymentId': 81,
            'transactionId': 'txn-81',
            'medium': 'short_video',
        },
    }


def test_emit_order_paid_conversion_skips_unattributed_order(monkeypatch):
    monkeypatch.setenv('CONTENT_PLATFORM_CONVERSION_WEBHOOK', 'http://127.0.0.1:3100/api/integrations/ecommerce/conversions')

    def unexpected_urlopen(*_args, **_kwargs):
        raise AssertionError('unattributed orders must not call the webhook')

    monkeypatch.setattr(growth_webhook, 'urlopen', unexpected_urlopen)

    order = SimpleNamespace(campaign_id=None)
    assert growth_webhook.emit_order_paid_conversion(order, SimpleNamespace()) is False


def test_emit_funnel_events_sends_landing_and_order_payloads(monkeypatch):
    captured = []

    class Response:
        status = 201

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    def fake_urlopen(request, timeout):
        captured.append((json.loads(request.data.decode('utf-8')), timeout))
        return Response()

    monkeypatch.setenv('CONTENT_PLATFORM_CONVERSION_WEBHOOK', 'http://127.0.0.1:3100/api/integrations/ecommerce/conversions')
    monkeypatch.setattr(growth_webhook, 'urlopen', fake_urlopen)
    monkeypatch.setattr(
        growth_webhook, '_resolve_product_external_id',
        lambda tenant_id, product_id: 'p-002' if str(product_id) == '101' else None,
    )

    assert growth_webhook.emit_landing_view_conversion(
        {
            'campaign_id': 'campaign_demo',
            'content_id': 'image_002',
            'source': 'xiaohongshu',
            'medium': 'social_image',
            'visitor_id': 'visitor-002',
            'product_id': '101',
        },
        tenant_id=7,
        request_path='/api/c/attribution/track/',
    ) is True

    order = SimpleNamespace(
        id=9002,
        tenant_id=7,
        order_no='ORD-9002',
        price=59.9,
        campaign_id='campaign_demo',
        content_id='image_002',
        attribution_source='xiaohongshu',
        attribution_medium='social_image',
    )
    assert growth_webhook.emit_order_created_conversion(order) is True

    landing, order_created = [item[0] for item in captured]
    assert landing['eventType'] == 'landing.view'
    assert landing['visitorId'] == 'visitor-002'
    assert landing['productExternalId'] == 'p-002'
    assert landing['payload']['productExternalId'] == 'p-002'
    assert landing['payload']['medium'] == 'social_image'
    assert order_created['eventType'] == 'order.created'
    assert order_created['externalOrderId'] == '9002'
    assert order_created['amount'] == 59.9
    assert all(timeout == 3 for _, timeout in captured)

def test_emit_lead_created_conversion_sends_contact_and_follow_up(monkeypatch):
    captured = {}

    class Response:
        status = 201
        def __enter__(self): return self
        def __exit__(self, *_args): return False

    def fake_urlopen(request, timeout):
        captured['payload'] = json.loads(request.data.decode('utf-8'))
        captured['timeout'] = timeout
        return Response()

    monkeypatch.setenv('CONTENT_PLATFORM_CONVERSION_WEBHOOK', 'http://127.0.0.1:3100/api/integrations/ecommerce/conversions')
    monkeypatch.setattr(growth_webhook, 'urlopen', fake_urlopen)
    monkeypatch.setattr(
        growth_webhook, '_resolve_product_external_id',
        lambda tenant_id, product_id: 'p-001',
    )
    lead = SimpleNamespace(
        id=31,
        tenant_id=7,
        product_id=101,
        product=SimpleNamespace(name='316 保温杯'),
        campaign_id='campaign_demo',
        content_id='image_001',
        source='xiaohongshu',
        medium='social_image',
        visitor_id='visitor-003',
        contact_name='徐先生',
        contact_type='wechat',
        contact_value='wx-growth-demo',
        demand='需要 20 件并确认到货时间',
        score=100,
        temperature='hot',
    )

    assert growth_webhook.emit_lead_created_conversion(lead) is True
    payload = captured['payload']
    assert captured['timeout'] == 3
    assert payload['eventType'] == 'lead.created'
    assert payload['externalOrderId'] == 'lead:31'
    assert payload['visitorId'] == 'visitor-003'
    assert payload['productExternalId'] == 'p-001'
    assert payload['payload']['contactValue'] == 'wx-growth-demo'
    assert payload['payload']['score'] == 100
    assert '316 保温杯' in payload['payload']['followUpDraft']

