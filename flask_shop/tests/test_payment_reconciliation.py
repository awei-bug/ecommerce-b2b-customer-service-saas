"""
支付对账完整性测试（覆盖剩余 P0：钱链路未端到端验证）。

验证「下单 → 发起支付 → 渠道回调 → 订单状态机 → 对账导出」整条链路：
- 金额一致：订单应付 == 支付单金额 == 对账导出成功金额。
- 状态一致：回调成功后订单 pending_pay → paid，支付单 created/paying → success。
- 幂等：重复回调不重复推进订单、不重复计钱。
- 边界：已支付订单不可再次发起支付；跨租户不可查他人支付单。

金额断言全部走「一致性」而非硬编码数字，天然兼容运费模板（不依赖具体运费规则）。
"""
import csv
import io

from flask_shop import db, models
from flask_shop.utils.tenant_query import tenant_context


# ---------- 夹具辅助 ----------

def _stock_product(app, tenant_id, name, price=99.5, number=100):
    """插入一个有库存的商品（跨租户初始化，绕过自动隔离），返回 id。"""
    with app.app_context():
        with tenant_context(disabled=True):
            p = models.Product(tenant_id=tenant_id, name=name, price=price, number=number)
            db.session.add(p)
            db.session.commit()
            return p.id


def _create_order(client, token, pid, number=2, address='对账测试地址'):
    rv = client.post(
        '/orders/',
        json={'items': [{'pid': pid, 'number': number}], 'address': address},
        headers={'token': token},
    )
    return rv.get_json()


def _pay_create(client, token, order_id):
    rv = client.post('/pay/create/', json={'order_id': order_id}, headers={'token': token})
    return rv.get_json()


def _mock_notify(client, token, out_trade_no, result='success'):
    rv = client.post(
        '/pay/mock/notify/',
        json={'out_trade_no': out_trade_no, 'result': result},
        headers={'token': token},
    )
    return rv.get_json()


# ---------- 全链路：下单 → 支付 → 状态机 ----------

def test_full_payment_chain(api, app):
    c, s = api['client'], api['seed']
    pid = _stock_product(app, s['id_a'], 'PAY-链路商品-A')

    # 1) 下单：应为待支付
    o = _create_order(c, s['token_a'], pid, number=3)
    assert o['status'] == 200, o
    order = o['data']
    order_id = order['id']
    order_price = float(order['price'])
    assert order['status'] == 'pending_pay'
    assert order_price > 0

    # 2) 发起支付：支付单金额必须等于订单应付
    p = _pay_create(c, s['token_a'], order_id)
    assert p['status'] == 200, p
    payment = p['data']['payment']
    out_trade_no = payment['out_trade_no']
    assert payment['status'] in ('created', 'paying')
    assert float(payment['amount']) == order_price  # 金额一致（关键对账断言）

    # 3) 渠道回调成功：首次非幂等
    n = _mock_notify(c, s['token_a'], out_trade_no)
    assert n['status'] == 200, n
    assert n['data']['idempotent'] is False
    assert n['data']['payment']['status'] == 'success'
    assert n['data']['order']['status'] == 'paid'  # 状态机已推进

    # 4) 订单详情：可见 success 支付单，金额仍一致
    d = c.get(f'/order/{order_id}/', headers={'token': s['token_a']}).get_json()
    assert d['status'] == 200
    pays = d['data']['payments']
    success = [x for x in pays if x['status'] == 'success']
    assert len(success) == 1
    assert float(success[0]['amount']) == order_price


# ---------- 幂等：重复回调不重复计钱 ----------

def test_mock_notify_idempotent(api, app):
    c, s = api['client'], api['seed']
    pid = _stock_product(app, s['id_a'], 'PAY-幂等商品-A')

    order = _create_order(c, s['token_a'], pid)['data']
    out_trade_no = _pay_create(c, s['token_a'], order['id'])['data']['payment']['out_trade_no']

    n1 = _mock_notify(c, s['token_a'], out_trade_no)
    n2 = _mock_notify(c, s['token_a'], out_trade_no)

    assert n1['data']['idempotent'] is False
    assert n2['data']['idempotent'] is True  # 第二次识别为重复回调
    assert n2['data']['payment']['status'] == 'success'

    # 订单只被推进一次；成功支付单只有一条
    d = c.get(f"/order/{order['id']}/", headers={'token': s['token_a']}).get_json()
    assert d['data']['status'] == 'paid'
    success = [x for x in d['data']['payments'] if x['status'] == 'success']
    assert len(success) == 1


# ---------- 对账导出：金额/笔数与实际支付一致 ----------

def test_reconciliation_export_matches_paid(api, app):
    c, s = api['client'], api['seed']
    pid = _stock_product(app, s['id_a'], 'PAY-对账商品-A')

    order = _create_order(c, s['token_a'], pid, number=2)['data']
    order_price = float(order['price'])
    out_trade_no = _pay_create(c, s['token_a'], order['id'])['data']['payment']['out_trade_no']
    _mock_notify(c, s['token_a'], out_trade_no)

    rv = c.get('/payments/export/', headers={'token': s['token_a']})
    assert rv.status_code == 200
    # 响应头汇总：成功金额与成功笔数
    assert rv.headers.get('X-Export-Count') is not None
    assert float(rv.headers['X-Export-Success-Amount']) == order_price

    # CSV 正文包含该支付单号且状态 success
    text = rv.get_data(as_text=True).lstrip('\ufeff')
    rows = list(csv.reader(io.StringIO(text)))
    body = rows[1:]
    matched = [r for r in body if out_trade_no in r]
    assert matched, 'CSV 未包含该支付单'
    assert 'success' in matched[0]


# ---------- 边界：已支付订单不可再次发起支付 ----------

def test_pay_create_rejects_paid_order(api, app):
    c, s = api['client'], api['seed']
    pid = _stock_product(app, s['id_a'], 'PAY-重复发起商品-A')

    order = _create_order(c, s['token_a'], pid)['data']
    out_trade_no = _pay_create(c, s['token_a'], order['id'])['data']['payment']['out_trade_no']
    _mock_notify(c, s['token_a'], out_trade_no)

    again = _pay_create(c, s['token_a'], order['id'])
    assert again['status'] == 400  # 仅待支付订单可发起支付


# ---------- 边界：支付失败不推进订单 ----------

def test_mock_notify_fail_keeps_pending(api, app):
    c, s = api['client'], api['seed']
    pid = _stock_product(app, s['id_a'], 'PAY-失败商品-A')

    order = _create_order(c, s['token_a'], pid)['data']
    out_trade_no = _pay_create(c, s['token_a'], order['id'])['data']['payment']['out_trade_no']

    n = _mock_notify(c, s['token_a'], out_trade_no, result='fail')
    assert n['status'] == 200
    assert n['data']['status'] == 'failed'

    d = c.get(f"/order/{order['id']}/", headers={'token': s['token_a']}).get_json()
    assert d['data']['status'] == 'pending_pay'  # 订单未被推进


# ---------- 隔离：跨租户不可查他人支付单 ----------

def test_cross_tenant_payment_detail_404(api, app):
    c, s = api['client'], api['seed']
    pid = _stock_product(app, s['id_a'], 'PAY-跨租户商品-A')

    order = _create_order(c, s['token_a'], pid)['data']
    out_trade_no = _pay_create(c, s['token_a'], order['id'])['data']['payment']['out_trade_no']

    # 租户 B 用自己的 token 查询 A 的支付单号 → 必须 404
    rv = c.get(f'/pay/{out_trade_no}/', headers={'token': s['token_b']}).get_json()
    assert rv['status'] == 404
