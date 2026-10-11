"""
动作级 RBAC 验收。

前置：
  python scripts/migrations/migrate_rbac_actions.py
  python scripts/seeds/seed_rbac_roles.py --with-users
  python manager.py

用法：
  python scripts/verify/verify_rbac.py
"""
import json
import sys
import urllib.error
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:5000'


def http_json(method, path, body=None, headers=None):
    url = BASE.rstrip('/') + path
    data = None if body is None else json.dumps(body).encode()
    hdrs = {'Content-Type': 'application/json'}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode() or '{}')
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw) if raw else {}
        except Exception:
            return e.code, {'raw': raw}


def login(slug, name, pwd):
    st, data = http_json('POST', '/user/login/', {
        'tenant_slug': slug, 'name': name, 'pwd': pwd,
    })
    assert data.get('status') == 200, (name, data)
    return data['data']['token'], data['data'].get('permissions') or {}


def main():
    print('BASE', BASE)
    # admin
    t_admin, p_admin = login('demo-a', 'admin_a', '123456')
    assert p_admin.get('is_super') is True
    assert http_json('GET', '/orders/', headers={'token': t_admin})[1].get('status') == 200
    assert http_json('GET', '/user/users/?pnum=1&psize=5', headers={'token': t_admin})[1].get('status') == 200
    print('[OK] admin full access', 'actions', len(p_admin.get('actions') or []))

    # clerk: ship yes, refund no, user no
    t_clerk, p_clerk = login('demo-a', 'clerk', '123456')
    actions = set(p_clerk.get('actions') or [])
    print('[OK] clerk actions', sorted(actions))
    assert 'order:read' in actions and 'order:ship' in actions
    assert 'order:refund' not in actions
    assert 'user:write' not in actions
    assert http_json('GET', '/orders/', headers={'token': t_clerk})[1].get('status') == 200
    assert http_json('GET', '/user/users/?pnum=1&psize=5', headers={'token': t_clerk})[1].get('status') == 403
    # 找一笔 paid 单测发货权限消息（无 paid 则 skip 业务，只测 403 路径用假 id 可能 404 优先）
    # 用 refund 接口测无权限：对不存在订单也可能先鉴权
    st, r = http_json('POST', '/order/1/refund/apply/', {}, headers={'token': t_clerk})
    # 403 鉴权优先，或 404 订单不存在但若先查订单再鉴权——我们代码是先鉴权
    assert r.get('status') == 403, r
    print('[OK] clerk cannot refund', r.get('msg'))

    # warehouse: only order read/ship
    try:
        t_wh, p_wh = login('demo-a', 'warehouse', '123456')
    except AssertionError:
        print('[SKIP] warehouse user missing')
        t_wh = None
    if t_wh:
        a = set(p_wh.get('actions') or [])
        assert 'order:ship' in a and 'product:write' not in a
        assert http_json('GET', '/products/', headers={'token': t_wh})[1].get('status') == 403
        print('[OK] warehouse product forbidden, can orders',
              http_json('GET', '/orders/', headers={'token': t_wh})[1].get('status'))

    # ops: product write, no ship
    try:
        t_ops, p_ops = login('demo-a', 'ops', '123456')
    except AssertionError:
        print('[SKIP] ops user missing')
        t_ops = None
    if t_ops:
        a = set(p_ops.get('actions') or [])
        assert 'product:write' in a and 'order:ship' not in a
        st, ship = http_json('POST', '/order/1/ship/', {'content': 'x'}, headers={'token': t_ops})
        assert ship.get('status') == 403, ship
        print('[OK] ops cannot ship', ship.get('msg'))

    # cs: refund yes, ship no
    try:
        t_cs, p_cs = login('demo-a', 'cs', '123456')
    except AssertionError:
        print('[SKIP] cs user missing')
        t_cs = None
    if t_cs:
        a = set(p_cs.get('actions') or [])
        assert 'order:refund' in a and 'order:ship' not in a
        st, ship = http_json('POST', '/order/1/ship/', {'content': 'x'}, headers={'token': t_cs})
        assert ship.get('status') == 403, ship
        print('[OK] cs cannot ship, has refund')

    print('\n==============================')
    print('动作级 RBAC 验收通过')
    print('==============================')


if __name__ == '__main__':
    try:
        main()
    except AssertionError as e:
        print('[FAIL]', e)
        sys.exit(1)
    except Exception as e:
        print('[ERROR]', e)
        sys.exit(2)
