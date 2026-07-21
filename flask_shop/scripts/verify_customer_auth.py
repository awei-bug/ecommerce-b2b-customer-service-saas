"""
C 端买家登录 + 下单 + mock 支付验收。

前置：
  python scripts/migrate_customer_auth.py
  python manager.py

用法：
  python scripts/verify_customer_auth.py
"""
import json
import sys
import urllib.error
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:5000'
SLUG = 'demo-a'
PHONE = '13900001111'


def http_json(method, path, body=None, headers=None):
    url = BASE.rstrip('/') + path
    data = None
    hdrs = {
        'Content-Type': 'application/json',
        'X-Tenant-Slug': SLUG,
    }
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


def main():
    print(f'BASE={BASE} slug={SLUG}')

    # 未登录下单应 401
    st, r = http_json('POST', '/api/c/orders/', {
        'address': 'x', 'items': [{'pid': 1, 'number': 1}]
    })
    assert r.get('status') == 401, r
    print('[OK] unauthenticated order -> 401')

    st, send = http_json('POST', '/api/c/auth/sms/send/', {'phone': PHONE})
    assert send.get('status') == 200, send
    code = (send.get('data') or {}).get('dev_code') or '123456'
    print(f'[OK] sms send dev_code={code}')

    st, login = http_json('POST', '/api/c/auth/sms/login/', {
        'phone': PHONE, 'code': code, 'nickname': '验收买家'
    })
    assert login.get('status') == 200, login
    token = login['data']['token']
    customer_id = login['data']['customer']['id']
    print(f'[OK] login customer_id={customer_id}')

    h = {'token': token}
    st, me = http_json('GET', '/api/c/auth/me/', headers=h)
    assert me.get('status') == 200 and me['data']['customer']['id'] == customer_id, me
    print('[OK] me')

    st, addr = http_json('POST', '/api/c/addresses/', {
        'contact_name': '验收',
        'contact_phone': PHONE,
        'region': '上海市浦东新区',
        'detail': '演示路 1 号',
        'is_default': 1,
    }, headers=h)
    assert addr.get('status') == 200, addr
    address_id = addr['data']['id']
    print(f'[OK] address id={address_id}')

    st, products = http_json('GET', '/api/c/products/', headers=h)
    assert products.get('status') == 200 and products.get('data'), products
    pid = products['data'][0]['id']

    st, order = http_json('POST', '/api/c/orders/', {
        'address_id': address_id,
        'items': [{'pid': pid, 'number': 1}],
    }, headers=h)
    assert order.get('status') == 200, order
    assert order['data'].get('customer_id') == customer_id, order
    oid = order['data']['id']
    print(f'[OK] order id={oid} status={order["data"]["status"]}')

    st, payc = http_json('POST', '/api/c/pay/create/', {'order_id': oid}, headers=h)
    assert payc.get('status') == 200, payc
    out = payc['data']['payment']['out_trade_no']
    st, paym = http_json('POST', '/api/c/pay/mock/', {'out_trade_no': out}, headers=h)
    assert paym.get('status') == 200, paym
    assert paym['data']['order']['status'] == 'paid', paym
    print('[OK] mock pay -> paid')

    st, orders = http_json('GET', '/api/c/orders/', headers=h)
    assert orders.get('status') == 200
    ids = {o['id'] for o in orders.get('data') or []}
    assert oid in ids
    print(f'[OK] my orders count={len(ids)}')

    # 错验证码
    st, bad = http_json('POST', '/api/c/auth/sms/login/', {
        'phone': PHONE, 'code': '000000'
    })
    # 开发模式固定码 123456 时 000000 应失败；若 SMS_DEV_CODE 被改另当别论
    assert bad.get('status') == 400, bad
    print('[OK] bad code rejected')

    print('\n==============================')
    print('Customer 登录骨架验收通过')
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
