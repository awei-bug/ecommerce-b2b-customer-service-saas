"""领域事件 outbox 与内网增量端点。

覆盖三条硬约束：事件与订单同事务、库存失败不残留事件、
端点默认关闭且按租户过滤可增量拉取。
"""
import json

from flask_shop import db, models
from flask_shop.utils.tenant_query import tenant_context


def _stock_product(app, tenant_id, name='事件测试商品', price=10.0, number=5):
    with app.app_context():
        with tenant_context(disabled=True):
            product = models.Product(
                tenant_id=tenant_id, name=name, price=price, number=number
            )
            db.session.add(product)
            db.session.commit()
            return product.id


def _create_order(client, token, pid, number=1, address='事件测试地址'):
    return client.post(
        '/orders/',
        json={'items': [{'pid': pid, 'number': number}], 'address': address},
        headers={'token': token},
    ).get_json()


def _event_count(app):
    with app.app_context():
        with tenant_context(disabled=True):
            return models.DomainEvent.query.count()


def test_order_created_writes_domain_event(api, app):
    client, seed = api['client'], api['seed']
    pid = _stock_product(app, seed['id_a'])
    before = _event_count(app)

    result = _create_order(client, seed['token_a'], pid)
    assert result['status'] == 200

    assert _event_count(app) == before + 1
    with app.app_context():
        with tenant_context(disabled=True):
            event = models.DomainEvent.query.order_by(models.DomainEvent.id.desc()).first()
            assert event.tenant_id == seed['id_a']
            assert event.event_type == 'order.created'
            assert event.aggregate_type == 'order'
            assert event.aggregate_id == str(result['data']['id'])
            payload = json.loads(event.payload)
            assert payload['order_no']
            assert payload['status'] == 'pending_pay'
            assert payload['number'] == 1


def test_stock_failure_leaves_no_event(api, app):
    client, seed = api['client'], api['seed']
    pid = _stock_product(app, seed['id_a'], name='库存不足商品', number=1)
    before = _event_count(app)

    result = _create_order(client, seed['token_a'], pid, number=99)
    assert result['status'] == 400
    assert _event_count(app) == before


def test_events_endpoint_fails_closed_and_streams_incrementally(api, app):
    client, seed = api['client'], api['seed']
    good = {'X-Events-Token': 'test-events-token'}

    assert client.get('/api/events', headers=good).status_code == 403

    app.config['EVENTS_API_ENABLED'] = True
    app.config['EVENTS_API_TOKEN'] = 'test-events-token'

    assert client.get('/api/events').status_code == 401
    assert client.get('/api/events', headers={'X-Events-Token': 'wrong'}).status_code == 401
    assert client.get('/api/events?after=abc', headers=good).status_code == 400

    pid = _stock_product(app, seed['id_a'])
    assert _create_order(client, seed['token_a'], pid)['status'] == 200

    first = client.get('/api/events?after=0&limit=10', headers=good)
    assert first.status_code == 200
    data = first.get_json()['data']
    assert len(data['events']) == 1
    assert data['events'][0]['tenant_id'] == seed['id_a']
    assert data['events'][0]['id'] == data['next_cursor']

    second = client.get(
        f"/api/events?after={data['next_cursor']}&limit=10", headers=good
    )
    assert second.get_json()['data']['events'] == []

    other = client.get(
        f"/api/events?after=0&tenant_id={seed['id_b']}", headers=good
    )
    assert other.get_json()['data']['events'] == []
