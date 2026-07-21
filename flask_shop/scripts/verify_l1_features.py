"""
验收：运费模板 / 上下架 / 角色动作权限 API
用法：先启动 manager.py，再 python scripts/verify_l1_features.py
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
        with urllib.request.urlopen(r, timeout=8) as resp:
            return json.loads(resp.read().decode() or '{}')
    except urllib.error.HTTPError as e:
        raw = e.read().decode() if e.fp else ''
        try:
            return json.loads(raw)
        except Exception:
            return {'status': e.code, 'msg': raw}


def login(slug, name, pwd='123456'):
    res = req('POST', '/user/login/', {
        'tenant_slug': slug,
        'name': name,
        'pwd': pwd,
    })
    assert res.get('status') == 200, res
    return res['data']['token'], res['data']


def main():
    print('BASE', BASE)
    token, data = login('demo-a', 'admin_a')
    h = {'token': token}
    print('[OK] admin login')

    # 运费列表 / 创建
    res = req('GET', '/freight/templates/', headers=h)
    assert res.get('status') == 200, res
    print('[OK] freight list', len(res.get('data') or []))

    # 试算
    res = req('POST', '/freight/preview/', {
        'goods_amount': 50, 'total_pieces': 1
    }, headers=h)
    assert res.get('status') == 200, res
    print('[OK] freight preview fee=', res['data']['freight_amount'])

    # 商品上下架
    products = req('GET', '/products/', headers=h)
    assert products.get('status') == 200, products
    plist = products.get('data') or []
    assert plist, 'no products'
    pid = plist[0]['id']
    res = req('POST', f'/product/{pid}/state/', {'state': 0}, headers=h)
    assert res.get('status') == 200, res
    print('[OK] product off-shelf', pid)
    res = req('POST', f'/product/{pid}/state/', {'state': 2}, headers=h)
    assert res.get('status') == 200, res
    print('[OK] product on-shelf', pid)

    # 动作码列表
    res = req('GET', '/permissions/actions/', headers=h)
    assert res.get('status') == 200 and res.get('data'), res
    print('[OK] action codes', len(res['data']))

    # 改角色 perm_codes（店员）
    roles = req('GET', '/roles/', headers=h)
    assert roles.get('status') == 200, roles
    clerk = next((r for r in roles['data'] if r['name'] == '店员'), None)
    if clerk:
        codes = clerk.get('perm_codes') or []
        res = req('PUT', f"/role/{clerk['id']}/", {
            'name': clerk['name'],
            'desc': clerk.get('desc') or '',
            'perm_codes': codes,
        }, headers=h)
        assert res.get('status') == 200, res
        print('[OK] update role perm_codes')
    else:
        print('[SKIP] no clerk role')

    # C 端运费试算
    res = req('POST', '/api/c/freight/preview/', {
        'goods_amount': 50, 'total_pieces': 2
    }, headers={'X-Tenant-Slug': 'demo-a', 'Content-Type': 'application/json'})
    assert res.get('status') == 200, res
    print('[OK] c freight preview', res['data']['freight_amount'])

    print('\n==============================')
    print('L1 功能验收通过')
    print('==============================')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as e:
        print('[FAIL]', e)
        sys.exit(1)
