"""
订单状态机 + 模拟支付闭环验收。

前置：
  1. python scripts/migrations/migrate_order_payment.py
  2. 服务已启动 python manager.py

用法：
  python scripts/verify/verify_order_payment.py
"""
import json
import sys
import urllib.error
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:5000'


def http_json(method, path, body=None, headers=None):
    url = BASE.rstrip('/') + path
    data = None
    hdrs = {'Content-Type': 'application/json'}
    if headers:
        hdrs.update(headers)
    if body is not None:
        data = json.dumps(body).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode('utf-8')
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode('utf-8')
        try:
            return e.code, json.loads(raw) if raw else {}
        except Exception:
            return e.code, {'raw': raw}
    except urllib.error.URLError as e:
        raise RuntimeError(f'无法连接 {url}: {e}') from e


def login(slug, name, pwd):
    status, data = http_json('POST', '/user/login/', {
        'tenant_slug': slug,
        'name': name,
        'pwd': pwd,
    })
    assert status == 200 and data.get('status') == 200, data
    return data['data']['token']


def main():
    print(f'BASE = {BASE}')
    token = login('demo-a', 'admin_a', '123456')
    h = {'token': token}

    # 取一个商品
    _, prod_resp = http_json('GET', '/products/', headers=h)
    assert prod_resp.get('status') == 200 and prod_resp.get('data'), prod_resp
    product = prod_resp['data'][0]
    pid = product['id']
    print(f'[OK] product id={pid} stock={product.get("number")}')

    # 创建订单
    _, create_resp = http_json('POST', '/orders/', {
        'address': '验收地址-状态机',
        'items': [{'pid': pid, 'number': 1}],
    }, headers=h)
    assert create_resp.get('status') == 200, create_resp
    order = create_resp['data']
    oid = order['id']
    assert order['status'] == 'pending_pay', order
    print(f'[OK] create order id={oid} no={order.get("order_no")} status={order["status"]}')

    # 非法发货
    _, bad_ship = http_json('POST', f'/order/{oid}/ship/', {}, headers=h)
    assert bad_ship.get('status') == 400, bad_ship
    print(f'[OK] ship before pay rejected: {bad_ship.get("msg")}')

    # 创建支付单
    _, pay_create = http_json('POST', '/pay/create/', {'order_id': oid, 'channel': 'mock'}, headers=h)
    assert pay_create.get('status') == 200, pay_create
    payment = pay_create['data']['payment']
    out_trade_no = payment['out_trade_no']
    print(f'[OK] payment created {out_trade_no}')

    # 模拟支付成功
    _, notify = http_json('POST', '/pay/mock/notify/', {
        'out_trade_no': out_trade_no,
        'result': 'success',
    }, headers=h)
    assert notify.get('status') == 200, notify
    assert notify['data']['order']['status'] == 'paid', notify
    print('[OK] mock pay -> order paid')

    # 幂等回调
    _, notify2 = http_json('POST', '/pay/mock/notify/', {
        'out_trade_no': out_trade_no,
        'result': 'success',
    }, headers=h)
    assert notify2.get('status') == 200 and notify2['data'].get('idempotent') is True, notify2
    print('[OK] notify idempotent')

    # 发货
    _, ship = http_json('POST', f'/order/{oid}/ship/', {
        'content': '顺丰 SF123456',
    }, headers=h)
    assert ship.get('status') == 200 and ship['data']['status'] == 'shipped', ship
    print('[OK] shipped')

    # 完成
    _, done = http_json('POST', f'/order/{oid}/complete/', {}, headers=h)
    assert done.get('status') == 200 and done['data']['status'] == 'completed', done
    print('[OK] completed')

    # 再走一笔：支付后售后全流程
    _, create2 = http_json('POST', '/orders/', {
        'address': '验收地址-退款',
        'items': [{'pid': pid, 'number': 1}],
    }, headers=h)
    assert create2.get('status') == 200, create2
    oid2 = create2['data']['id']
    _, p2 = http_json('POST', '/pay/create/', {'order_id': oid2}, headers=h)
    out2 = p2['data']['payment']['out_trade_no']
    http_json('POST', '/pay/mock/notify/', {'out_trade_no': out2, 'result': 'success'}, headers=h)

    _, apply_r = http_json('POST', f'/order/{oid2}/refund/apply/', {}, headers=h)
    assert apply_r.get('status') == 200 and apply_r['data']['status'] == 'refunding', apply_r
    print('[OK] refund apply')

    _, approve = http_json('POST', f'/order/{oid2}/refund/approve/', {'reason': '验收退款'}, headers=h)
    assert approve.get('status') == 200, approve
    assert approve['data']['order']['status'] == 'refunded', approve
    assert approve['data']['refund']['status'] == 'success', approve
    print('[OK] refund approve (mock)')

    # 取消待支付订单
    _, create3 = http_json('POST', '/orders/', {
        'address': '验收地址-取消',
        'items': [{'pid': pid, 'number': 1}],
    }, headers=h)
    oid3 = create3['data']['id']
    _, cancel = http_json('POST', f'/order/{oid3}/cancel/', {'reason': '不想要了'}, headers=h)
    assert cancel.get('status') == 200 and cancel['data']['status'] == 'closed', cancel
    print('[OK] cancel pending_pay -> closed')

    print('\n==============================')
    print('订单状态机 + 模拟支付验收通过')
    print('==============================')


if __name__ == '__main__':
    try:
        main()
    except AssertionError as e:
        print(f'\n[FAIL] {e}')
        sys.exit(1)
    except Exception as e:
        print(f'\n[ERROR] {e}')
        sys.exit(2)
