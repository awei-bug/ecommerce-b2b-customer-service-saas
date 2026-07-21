"""
双租户数据隔离回归测试。

核心目标：一旦某个视图忘记加 tenant_id 过滤，这里就必须失败。
任何一条「跨租户能读到对方数据」都意味着 SaaS 信任边界被击穿。
"""
import pytest

from flask_shop import models
from flask_shop.utils.tenant import TenantError, tenant_filter


def _names(data):
    if isinstance(data, dict):
        inner = data.get('data')
        if isinstance(inner, list):
            return {d.get('name') for d in inner if isinstance(d, dict)}
        if isinstance(inner, dict):  # 用户列表是 {data:[...]}
            return {d.get('name') for d in (inner.get('data') or []) if isinstance(d, dict)}
    if isinstance(data, list):
        return {d.get('name') for d in data if isinstance(d, dict)}
    return set()


def _ship_nos(data):
    items = data.get('data') if isinstance(data, dict) else data
    if isinstance(items, list):
        return {d.get('shipment_no') for d in items if isinstance(d, dict)}
    return set()


def _order_nos(data):
    items = data.get('data') if isinstance(data, dict) else data
    if isinstance(items, list):
        return {d.get('order_no') for d in items if isinstance(d, dict)}
    return set()


# ---------- 列表隔离 ----------

def test_product_list_isolation(api):
    c, s = api['client'], api['seed']
    a = c.get('/products/', headers={'token': s['token_a']}).get_json()
    b = c.get('/products/', headers={'token': s['token_b']}).get_json()
    assert a['status'] == 200 and b['status'] == 200
    na, nb = _names(a), _names(b)
    assert 'A-唯一商品-xyz' in na and 'B-唯一商品-xyz' not in na
    assert 'B-唯一商品-xyz' in nb and 'A-唯一商品-xyz' not in nb


def test_order_list_isolation(api):
    c, s = api['client'], api['seed']
    a = c.get('/orders/', headers={'token': s['token_a']}).get_json()
    b = c.get('/orders/', headers={'token': s['token_b']}).get_json()
    assert a['status'] == 200 and b['status'] == 200
    oa, ob = _order_nos(a), _order_nos(b)
    assert 'A-ORD-1' in oa and 'B-ORD-1' not in oa
    assert 'B-ORD-1' in ob and 'A-ORD-1' not in ob


def test_user_list_isolation(api):
    c, s = api['client'], api['seed']
    a = c.get('/user/users/?pnum=1&psize=50', headers={'token': s['token_a']}).get_json()
    b = c.get('/user/users/?pnum=1&psize=50', headers={'token': s['token_b']}).get_json()
    assert a['status'] == 200 and b['status'] == 200
    na, nb = _names(a), _names(b)
    assert 'admin_a' in na and 'admin_b' not in na
    assert 'admin_b' in nb and 'admin_a' not in nb


def test_category_list_isolation(api):
    c, s = api['client'], api['seed']
    a = c.get('/categorys/', headers={'token': s['token_a']}).get_json()
    b = c.get('/categorys/', headers={'token': s['token_b']}).get_json()
    assert a['status'] == 200 and b['status'] == 200
    na, nb = _names(a), _names(b)
    assert 'A-类目-唯一' in na and 'B-类目-唯一' not in na
    assert 'B-类目-唯一' in nb and 'A-类目-唯一' not in nb


def test_role_list_isolation(api):
    c, s = api['client'], api['seed']
    a = c.get('/roles/', headers={'token': s['token_a']}).get_json()
    b = c.get('/roles/', headers={'token': s['token_b']}).get_json()
    assert a['status'] == 200 and b['status'] == 200
    na, nb = _names(a), _names(b)
    assert 'A-角色-唯一' in na and 'B-角色-唯一' not in na
    assert 'B-角色-唯一' in nb and 'A-角色-唯一' not in nb


def test_shipment_list_isolation(api):
    c, s = api['client'], api['seed']
    a = c.get('/shipments/', headers={'token': s['token_a']}).get_json()
    b = c.get('/shipments/', headers={'token': s['token_b']}).get_json()
    assert a['status'] == 200 and b['status'] == 200
    sa, sb = _ship_nos(a), _ship_nos(b)
    assert 'A-SHIP-1' in sa and 'B-SHIP-1' not in sa
    assert 'B-SHIP-1' in sb and 'A-SHIP-1' not in sb


def test_freight_list_isolation(api):
    c, s = api['client'], api['seed']
    a = c.get('/freight/templates/', headers={'token': s['token_a']}).get_json()
    b = c.get('/freight/templates/', headers={'token': s['token_b']}).get_json()
    assert a['status'] == 200 and b['status'] == 200
    na, nb = _names(a), _names(b)
    assert 'A-运费-唯一' in na and 'B-运费-唯一' not in na
    assert 'B-运费-唯一' in nb and 'A-运费-唯一' not in nb


# ---------- 跨租户详情必须 404 ----------

def test_cross_tenant_product_detail_404(api):
    c, s = api['client'], api['seed']
    rv = c.get(f"/product/{s['product_b'].id}/", headers={'token': s['token_a']})
    assert rv.get_json()['status'] == 404


def test_cross_tenant_order_detail_404(api):
    c, s = api['client'], api['seed']
    rv = c.get(f"/order/{s['order_b'].id}/", headers={'token': s['token_a']})
    assert rv.get_json()['status'] == 404


def test_cross_tenant_shipment_detail_404(api):
    c, s = api['client'], api['seed']
    rv = c.get(f"/shipment/{s['shipment_b'].id}/", headers={'token': s['token_a']})
    assert rv.get_json()['status'] == 404


# ---------- 鉴权边界 ----------

def test_header_tenant_mismatch_403(api):
    c, s = api['client'], api['seed']
    rv = c.get('/products/', headers={'token': s['token_a'], 'X-Tenant-Id': str(s['id_b'])})
    assert rv.get_json()['status'] == 403


def test_unauthenticated_returns_401(api):
    c = api['client']
    rv = c.get('/products/')
    assert rv.get_json()['status'] == 401


# ---------- 隔离机制护栏（单元测试） ----------

def test_tenant_filter_helper_scopes_correctly(app):
    with app.app_context():
        from flask import g
        g.tenant_id = app._seed_ctx['id_a']
        rows = tenant_filter(models.Product).all()
        names = {p.name for p in rows}
        assert 'A-唯一商品-xyz' in names
        assert 'B-唯一商品-xyz' not in names

        g.tenant_id = None
        with pytest.raises(TenantError):
            tenant_filter(models.Product).all()


# ---------- 方案 2：before_compile 自动隔离 ----------

def test_auto_isolation_without_explicit_filter(app):
    """即使业务代码完全不写 tenant_id 过滤，查询也应被自动隔离。"""
    from flask import g
    with app.app_context():
        g.tenant_id = app._seed_ctx['id_a']
        # 故意不写任何 tenant_id 过滤
        rows = models.Product.query.all()
        names = {p.name for p in rows}
        assert 'A-唯一商品-xyz' in names
        assert 'B-唯一商品-xyz' not in names


def test_auto_isolation_across_tenant_models(app):
    """自动隔离对多种带 tenant_id 的模型统一生效。"""
    from flask import g
    with app.app_context():
        tid = app._seed_ctx['id_a']
        g.tenant_id = tid
        assert all(o.tenant_id == tid for o in models.Order.query.all())
        assert all(u.tenant_id == tid for u in models.User.query.all())
        assert all(c.tenant_id == tid for c in models.Category.query.all())
        assert all(r.tenant_id == tid for r in models.Role.query.all())


def test_tenant_and_menu_models_exempt(app):
    """无 tenant_id 列的模型（Tenant/Menu）应豁免隔离，可跨租户查询。"""
    from flask import g
    with app.app_context():
        g.tenant_id = app._seed_ctx['id_a']
        # Tenant 无 tenant_id 列 -> 两租户都能查到（不被隔离）
        tenants = models.Tenant.query.all()
        assert len(tenants) >= 2
        # Menu 模型结构上无 tenant_id 列 -> 自动豁免
        assert 'tenant_id' not in models.Menu.__table__.columns
        # Menu 查询执行不抛异常（无论是否有种子数据）
        assert isinstance(models.Menu.query.all(), list)


def test_isolation_bypass_reveals_cross_tenant(app):
    """反向控制：禁用自动隔离后能看到跨租户数据，证明正常时护栏确实生效。

    平台中台 / 数据迁移用 tenant_context(disabled=True) 显式跨租户。
    """
    from flask import g
    from flask_shop.utils.tenant_query import tenant_context
    with app.app_context():
        g.tenant_id = app._seed_ctx['id_a']
        with tenant_context(disabled=True):
            rows = models.Product.query.all()
        names = {p.name for p in rows}
        assert 'B-唯一商品-xyz' in names  # 若无护栏则会串数据
