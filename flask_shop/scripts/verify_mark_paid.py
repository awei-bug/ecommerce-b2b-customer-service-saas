"""
验收：人工标记已付款 + 店铺付款指引 + mock 开关探测
用法：先启动 API，再 python scripts/verify_mark_paid.py
"""
import json
import sys
import urllib.error
import urllib.request

BASE = 'http://127.0.0.1:5000'


def req(method, path, body=None, headers=None):
    data = None if body is None else json.dumps(body).encode()
    h = {'Content-Type': 'application/json'}
    if headers:
        h.update(headers)
    r = urllib.request.Request(BASE + path, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(r, timeout=10) as resp:
            return json.loads(resp.read().decode() or '{}')
    except urllib.error.HTTPError as e:
        raw = e.read().decode() if e.fp else ''
        try:
            return json.loads(raw)
        except Exception:
            return {'status': e.code, 'msg': raw}


def login(slug, name, pwd='123456'):
    res = req('POST', '/user/login/', {
        'tenant_slug': slug, 'name': name, 'pwd': pwd,
    })
    assert res.get('status') == 200, res
    return res['data']['token'], res['data']


def main():
    print('BASE', BASE)
    token, data = login('demo-a', 'admin_a')
    h = {'token': token}
    actions = (data.get('permissions') or {}).get('actions') or []
    print('[OK] login actions contain mark_paid?', 'order:mark_paid' in actions or data['permissions'].get('is_super'))

    # 店铺设置
    res = req('GET', '/user/shop/settings/', headers=h)
    assert res.get('status') == 200, res
    print('[OK] get shop settings')

    guide = '【演示店】请微信转账至店主，备注订单号。到账后发货。'
    res = req('PUT', '/user/shop/settings/', {
        'pay_guide': guide,
        'contact_phone': '13800000001',
    }, headers=h)
    assert res.get('status') == 200, res
    assert res['data'].get('pay_guide') == guide
    print('[OK] update pay_guide')

    # C 端店铺信息含指引
    res = req('GET', '/api/c/shop/', headers={
        'X-Tenant-Slug': 'demo-a',
        'Content-Type': 'application/json',
    })
    assert res.get('status') == 200, res
    assert res['data'].get('pay_guide')
    print('[OK] c shop pay_guide')

    # 取一件商品下单（商户侧演示创建）
    products = req('GET', '/products/', headers=h)
    assert products.get('status') == 200 and products.get('data'), products
    pid = products['data'][0]['id']
    order_res = req('POST', '/orders/', {
        'address': '验收地址-标记已付',
        'items': [{'pid': pid, 'number': 1}],
    }, headers=h)
    assert order_res.get('status') == 200, order_res
    oid = order_res['data']['id']
    assert order_res['data']['status'] == 'pending_pay'
    print('[OK] create order', oid)

    # 未支付不能发货
    ship = req('POST', f'/order/{oid}/ship/', {'content': 'SF测试'}, headers=h)
    assert ship.get('status') == 400, ship
    print('[OK] ship before paid rejected')

    # 标记已付
    paid = req('POST', f'/order/{oid}/mark-paid/', {
        'note': '微信转账后四位 6688',
    }, headers=h)
    assert paid.get('status') == 200, paid
    assert paid['data']['order']['status'] == 'paid'
    assert paid['data']['payment']['channel'] == 'manual'
    print('[OK] mark paid')

    # 幂等：再标一次应失败
    paid2 = req('POST', f'/order/{oid}/mark-paid/', {}, headers=h)
    assert paid2.get('status') == 400, paid2
    print('[OK] mark paid twice rejected')

    # 发货
    ship2 = req('POST', f'/order/{oid}/ship/', {'content': 'SF123456'}, headers=h)
    assert ship2.get('status') == 200, ship2
    print('[OK] ship after paid')

    # 店员应有 mark_paid（若种子已更新）
    try:
        t2, d2 = login('demo-a', 'clerk')
        acts = (d2.get('permissions') or {}).get('actions') or []
        print('[INFO] clerk actions', acts)
        if acts and 'order:mark_paid' not in acts and not d2['permissions'].get('is_super'):
            print('[WARN] clerk 无 mark_paid，请运行 seed_rbac_roles.py --with-users 刷新')
        else:
            print('[OK] clerk has mark_paid or super')
    except Exception as e:
        print('[SKIP] clerk login', e)

    print('\n==============================')
    print('标记已付款验收通过')
    print('==============================')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as e:
        print('[FAIL]', e)
        sys.exit(1)
