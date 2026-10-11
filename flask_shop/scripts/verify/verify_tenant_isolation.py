"""
双租户隔离验收脚本（阶段 0）。

前置：
  1. 已执行 python scripts/seeds/seed_tenants.py
  2. 服务已启动：python manager.py  （默认 http://127.0.0.1:5000）

用法：
  python scripts/verify/verify_tenant_isolation.py
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


def login(slug, name, pwd):
    status, data = http_json('POST', '/user/login/', {
        'tenant_slug': slug,
        'name': name,
        'pwd': pwd,
    })
    assert status == 200 and data.get('status') == 200, f'登录失败 {slug}: {data}'
    token = data['data']['token']
    tenant = data['data']['tenant']
    print(f'[OK] 登录 {slug} tenant_id={tenant["id"]}')
    return token, tenant


def main():
    print(f'BASE = {BASE}')
    token_a, tenant_a = login('demo-a', 'admin_a', '123456')
    token_b, tenant_b = login('demo-b', 'admin_b', '123456')
    assert tenant_a['id'] != tenant_b['id'], '两个租户 id 不应相同'

    # 商品列表隔离
    _, products_a = http_json('GET', '/products/', headers={'token': token_a})
    _, products_b = http_json('GET', '/products/', headers={'token': token_b})
    assert products_a.get('status') == 200, products_a
    assert products_b.get('status') == 200, products_b
    names_a = {p['name'] for p in products_a.get('data') or []}
    names_b = {p['name'] for p in products_b.get('data') or []}
    print(f'[INFO] A 商品: {names_a}')
    print(f'[INFO] B 商品: {names_b}')
    assert names_a, 'A 应有商品'
    assert names_b, 'B 应有商品'
    assert names_a.isdisjoint(names_b), 'A/B 商品列表不应有交集（串数据）'

    # 跨租户读详情：A 的 token 读 B 的商品 id → 404
    b_product_id = products_b['data'][0]['id']
    status, detail = http_json('GET', f'/product/{b_product_id}/', headers={'token': token_a})
    print(f'[INFO] A 读 B 商品 id={b_product_id} => status={detail.get("status")} msg={detail.get("msg")}')
    assert detail.get('status') == 404, '跨租户读取商品应返回 404'

    # 订单隔离
    _, orders_a = http_json('GET', '/orders/', headers={'token': token_a})
    _, orders_b = http_json('GET', '/orders/', headers={'token': token_b})
    ids_a = {o['id'] for o in orders_a.get('data') or []}
    ids_b = {o['id'] for o in orders_b.get('data') or []}
    print(f'[INFO] A 订单 ids: {ids_a}')
    print(f'[INFO] B 订单 ids: {ids_b}')
    assert ids_a.isdisjoint(ids_b), 'A/B 订单不应有交集'

    if ids_b:
        bid = next(iter(ids_b))
        _, od = http_json('GET', f'/order/{bid}/', headers={'token': token_a})
        assert od.get('status') == 404, '跨租户读订单应 404'
        print(f'[OK] A 读 B 订单 id={bid} => 404')

    # 用户列表隔离
    _, users_a = http_json('GET', '/user/users/?pnum=1&psize=50', headers={'token': token_a})
    names_ua = {u['name'] for u in (users_a.get('data') or {}).get('data') or []}
    assert 'admin_a' in names_ua
    assert 'admin_b' not in names_ua, 'A 用户列表不应出现 B 的员工'
    print(f'[OK] 用户列表隔离 names={names_ua}')

    # Header 租户与 token 不一致应 403
    _, mismatch = http_json(
        'GET',
        '/products/',
        headers={'token': token_a, 'X-Tenant-Id': str(tenant_b['id'])},
    )
    print(f'[INFO] tokenA + X-Tenant-Id=B => {mismatch}')
    assert mismatch.get('status') == 403, '租户不一致应 403'

    print('\n==============================')
    print('全部验收通过：双租户数据隔离有效')
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
