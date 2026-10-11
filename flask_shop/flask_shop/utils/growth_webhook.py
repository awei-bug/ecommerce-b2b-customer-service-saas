"""Report attributed commerce funnel events to the content growth service."""
import json
import os
from urllib.error import URLError
from urllib.request import Request, urlopen


def _resolve_product_external_id(tenant_id, product_id):
    """product_id → 数据中心 external_id，让转化能归到具体商品维度。"""
    if not product_id:
        return None
    try:
        from flask_shop import db, models
        resolved_product_id = int(product_id) if str(product_id).isdigit() else product_id
        row = (db.session.query(models.ProductKnowledge)
               .filter_by(tenant_id=tenant_id, product_id=resolved_product_id)
               .first())
        return row.external_id if row else None
    except Exception:
        return None


def _order_product_external_id(order):
    """订单 → 首个明细商品的外部 ID。"""
    try:
        details = list(getattr(order, 'order_detail', None) or [])
        if not details:
            return None
        return _resolve_product_external_id(
            getattr(order, 'tenant_id', None), getattr(details[0], 'pid', None))
    except Exception:
        return None


def _emit_conversion(payload):
    url = (os.getenv('CONTENT_PLATFORM_CONVERSION_WEBHOOK') or '').strip()
    if not url or not payload.get('campaignId'):
        return False

    token = (os.getenv('CONTENT_PLATFORM_WEBHOOK_TOKEN') or '').strip()
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['X-Integration-Token'] = token
    try:
        request = Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
            headers=headers,
            method='POST',
        )
        with urlopen(request, timeout=3) as response:
            return 200 <= int(response.status) < 300
    except (OSError, URLError, ValueError) as error:
        # Reporting must never break storefront browsing, ordering, or payment.
        print('growth conversion webhook failed:', error)
        return False


def _with_product_external_id(payload, external_id):
    if not external_id:
        return payload
    payload['productExternalId'] = external_id
    payload.setdefault('payload', {})['productExternalId'] = external_id
    return payload


def emit_landing_view_conversion(attribution, tenant_id, request_path=None):
    attribution = attribution or {}
    external_id = _resolve_product_external_id(tenant_id, attribution.get('product_id'))
    payload = {
        'eventType': 'landing.view',
        'campaignId': attribution.get('campaign_id'),
        'contentId': attribution.get('content_id'),
        'source': attribution.get('source'),
        'externalTenantId': str(tenant_id or ''),
        'visitorId': attribution.get('visitor_id'),
        'payload': {
            'medium': attribution.get('medium'),
            'path': request_path,
            'productId': attribution.get('product_id'),
        },
    }
    return _emit_conversion(_with_product_external_id(payload, external_id))


def emit_lead_created_conversion(lead):
    product = getattr(lead, 'product', None)
    name = (getattr(lead, 'contact_name', None) or '您好').strip()
    product_name = getattr(product, 'name', None) or '您关注的商品'
    demand = (getattr(lead, 'demand', None) or '').strip()
    detail = f'，关于“{demand[:80]}”' if demand else ''
    tenant_id = getattr(lead, 'tenant_id', None)
    product_id = getattr(lead, 'product_id', None)
    external_id = _resolve_product_external_id(tenant_id, product_id)
    payload = {
        'eventType': 'lead.created',
        'campaignId': getattr(lead, 'campaign_id', None),
        'contentId': getattr(lead, 'content_id', None),
        'source': getattr(lead, 'source', None),
        'externalTenantId': str(tenant_id or ''),
        'externalOrderId': f"lead:{getattr(lead, 'id', '')}",
        'visitorId': getattr(lead, 'visitor_id', None),
        'payload': {
            'leadId': str(getattr(lead, 'id', '') or ''),
            'contactName': getattr(lead, 'contact_name', None),
            'contactType': getattr(lead, 'contact_type', None),
            'contactValue': getattr(lead, 'contact_value', None),
            'demand': getattr(lead, 'demand', None),
            'productId': product_id,
            'productName': product_name,
            'medium': getattr(lead, 'medium', None),
            'score': int(getattr(lead, 'score', 0) or 0),
            'temperature': getattr(lead, 'temperature', None),
            'followUpDraft': f'{name}，已收到您对{product_name}的咨询{detail}。我可以继续为您确认价格、库存和交付信息。',
        },
    }
    return _emit_conversion(_with_product_external_id(payload, external_id))


def emit_order_created_conversion(order):
    external_id = _order_product_external_id(order)
    payload = {
        'eventType': 'order.created',
        'campaignId': getattr(order, 'campaign_id', None),
        'contentId': getattr(order, 'content_id', None),
        'source': getattr(order, 'attribution_source', None),
        'externalTenantId': str(getattr(order, 'tenant_id', '') or ''),
        'externalOrderId': str(getattr(order, 'id', '') or ''),
        'amount': float(getattr(order, 'price', 0) or 0),
        'currency': os.getenv('SHOP_CURRENCY', 'CNY'),
        'payload': {
            'orderNo': getattr(order, 'order_no', None),
            'medium': getattr(order, 'attribution_medium', None),
        },
    }
    return _emit_conversion(_with_product_external_id(payload, external_id))


def emit_order_paid_conversion(order, payment):
    external_id = _order_product_external_id(order)
    payload = {
        'eventType': 'order.paid',
        'campaignId': getattr(order, 'campaign_id', None),
        'contentId': getattr(order, 'content_id', None),
        'source': getattr(order, 'attribution_source', None),
        'externalTenantId': str(getattr(order, 'tenant_id', '') or ''),
        'externalOrderId': str(getattr(order, 'id', '') or ''),
        'amount': float(getattr(order, 'price', 0) or 0),
        'currency': os.getenv('SHOP_CURRENCY', 'CNY'),
        'occurredAt': getattr(payment, 'paid_at', None).isoformat() if getattr(payment, 'paid_at', None) else None,
        'payload': {
            'orderNo': getattr(order, 'order_no', None),
            'paymentId': getattr(payment, 'id', None),
            'transactionId': getattr(payment, 'transaction_id', None),
            'medium': getattr(order, 'attribution_medium', None),
        },
    }
    return _emit_conversion(_with_product_external_id(payload, external_id))
