"""
双租户隔离测试夹具。

设计要点：
- 用临时 SQLite 文件代替 MySQL，保证 CI 可移植、不依赖外部数据库。
- 模型无 MySQL 专有类型，SQLite 完全兼容。
- 每个测试在两租户（A / B）各灌入业务数据，名称带唯一标记，
  便于断言「A 的列表不含 B 的数据」。
- 测试用户赋予「超级管理员」角色（按名称命中），绕过 RBAC 只读校验，
  让隔离测试只验证「租户边界」，不被权限干扰。
- 若任一视图忘记加 tenant_id 过滤，跨租户详情会返回 404、列表会串数据，
  下面的用例会失败 —— 这正是我们要的回归护栏。
"""
import os
import tempfile

import pytest

from flask_shop import create_app, db, models
from flask_shop.utils.token import generate_token
from flask_shop.utils.tenant_query import tenant_context


def _seed(app):
    # 播种是跨租户的初始化操作，必须显式绕过自动租户过滤，
    # 否则在 TENANT_STRICT=1 下（CI）会因未绑租户而报错。
    with tenant_context(disabled=True):
        ta = models.Tenant(name='测试租户A', slug='test-a', status=1)
        tb = models.Tenant(name='测试租户B', slug='test-b', status=1)
        db.session.add_all([ta, tb])
        db.session.commit()

        # 超级管理员：按名称命中 _is_super_role，免去配置菜单/权限码
        ra = models.Role(tenant_id=ta.id, name='超级管理员')
        rb = models.Role(tenant_id=tb.id, name='超级管理员')
        db.session.add_all([ra, rb])
        db.session.commit()

        ua = models.User(tenant_id=ta.id, name='admin_a', role_id=ra.id)
        ua.password = '123456'
        ub = models.User(tenant_id=tb.id, name='admin_b', role_id=rb.id)
        ub.password = '123456'
        db.session.add_all([ua, ub])
        db.session.commit()

        # 业务数据：名称带唯一标记
        pa = models.Product(tenant_id=ta.id, name='A-唯一商品-xyz', price=10)
        pb = models.Product(tenant_id=tb.id, name='B-唯一商品-xyz', price=20)
        ca = models.Category(tenant_id=ta.id, name='A-类目-唯一')
        cb = models.Category(tenant_id=tb.id, name='B-类目-唯一')
        oa = models.Order(tenant_id=ta.id, order_no='A-ORD-1', price=10, status='pending_pay')
        ob = models.Order(tenant_id=tb.id, order_no='B-ORD-1', price=20, status='paid')
        sa = models.Shipment(tenant_id=ta.id, shipment_no='A-SHIP-1', status='inquiry')
        sb = models.Shipment(tenant_id=tb.id, shipment_no='B-SHIP-1', status='booked')
        fra = models.FreightTemplate(tenant_id=ta.id, name='A-运费-唯一')
        frb = models.FreightTemplate(tenant_id=tb.id, name='B-运费-唯一')
        # 非超级角色，仅用于「角色列表隔离」断言
        rola = models.Role(tenant_id=ta.id, name='A-角色-唯一')
        rolb = models.Role(tenant_id=tb.id, name='B-角色-唯一')
        db.session.add_all([pa, pb, ca, cb, oa, ob, sa, sb, fra, frb, rola, rolb])
        db.session.commit()

        token_a = generate_token({'typ': 'merchant', 'staff_id': ua.id, 'tenant_id': ta.id})
        token_b = generate_token({'typ': 'merchant', 'staff_id': ub.id, 'tenant_id': tb.id})

        return {
            'ta': ta, 'tb': tb,
            'token_a': token_a, 'token_b': token_b,
            'product_a': pa, 'product_b': pb,
            'order_a': oa, 'order_b': ob,
            'shipment_a': sa, 'shipment_b': sb,
            'id_a': ta.id, 'id_b': tb.id,
        }


@pytest.fixture
def app():
    # Flask-SQLAlchemy 3.x 在 create_app 内的 db.init_app() 时就按当时 config 绑定 engine，
    # 因此必须在 create_app 之前把 URI 改成临时 SQLite，否则会误连开发用 MySQL 并污染真库。
    from config import TestingConfig

    fd, path = tempfile.mkstemp(suffix='.sqlite')
    os.close(fd)
    uri = f'sqlite:///{path}'

    old_uri = TestingConfig.SQLALCHEMY_DATABASE_URI
    TestingConfig.SQLALCHEMY_DATABASE_URI = uri
    try:
        app = create_app('test')
        app.config['TESTING'] = True
        with app.app_context():
            db.create_all()
            app._seed_ctx = _seed(app)
            yield app
            db.session.remove()
            db.drop_all()
    finally:
        TestingConfig.SQLALCHEMY_DATABASE_URI = old_uri
        try:
            os.unlink(path)
        except OSError:
            pass


@pytest.fixture
def api(app):
    client = app.test_client()
    return {'client': client, 'seed': app._seed_ctx}
