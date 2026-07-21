"""
阶段 0 种子数据：两个租户 + 各自管理员 + 示例商品，用于隔离验收。

用法（在 flask_shop 目录下）：
  1. 配置 .env（可复制 .env.example）
  2. 确保 MySQL 中已创建空库（默认 flask_shop_saas）
  3. python scripts/seed_tenants.py

默认行为：
  - 仅 db.create_all()（不删表）
  - 若 demo-a / demo-b 已存在则跳过并提示

危险操作（会清空当前库全部表）需显式确认：
  python scripts/seed_tenants.py --reset
  且环境变量 ALLOW_DB_RESET=1
"""
import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# 不依赖 manager.py（避免本机未装 flask_migrate 时无法跑种子）
from flask_shop import create_app, db, models  # noqa: E402

app = create_app('develop')


def ensure_menus():
    """平台级菜单模板（共享），按 name 幂等创建。"""
    specs_l1 = [
        ('用户管理', 'users'),
        ('权限管理', 'rights'),
        ('商品管理', 'goods'),
        ('订单管理', 'orders'),
        ('数据统计', 'reports'),
    ]
    menus = {}
    for name, path in specs_l1:
        m = models.Menu.query.filter_by(name=name).first()
        if not m:
            m = models.Menu(name=name, path=path, level=1)
            db.session.add(m)
            db.session.flush()
        menus[name] = m

    children = [
        ('用户列表', 'user_list', '用户管理'),
        ('角色列表', 'role_list', '权限管理'),
        ('权限列表', 'author_list', '权限管理'),
        ('商品列表', 'product_list', '商品管理'),
        ('分类参数', 'attribute_list', '商品管理'),
        ('商品分类', 'group_list', '商品管理'),
        ('订单列表', 'order_list', '订单管理'),
        ('数据报表', 'data_list', '数据统计'),
    ]
    all_menus = list(menus.values())
    for name, path, parent_name in children:
        m = models.Menu.query.filter_by(name=name).first()
        if not m:
            m = models.Menu(name=name, path=path, level=2, pid=menus[parent_name].id)
            db.session.add(m)
            db.session.flush()
        all_menus.append(m)
    return all_menus


def seed_tenant(slug, name, admin_name, product_name, product_price, address, phone, email):
    tenant = models.Tenant.query.filter_by(slug=slug).first()
    if tenant:
        print(f'   skip tenant {slug} (already exists, id={tenant.id})')
        return tenant, False

    tenant = models.Tenant(name=name, slug=slug, status=1, plan_code='free')
    db.session.add(tenant)
    db.session.flush()

    all_menus = ensure_menus()
    role = models.Role(tenant_id=tenant.id, name='超级管理员', desc=f'{name}全部权限')
    role.menus = list(all_menus)
    db.session.add(role)
    db.session.flush()

    user = models.User(
        tenant_id=tenant.id,
        name=admin_name,
        nick_name=f'{name}管理员',
        phone=phone,
        email=email,
        role_id=role.id,
    )
    user.password = '123456'
    db.session.add(user)
    db.session.flush()

    cat = models.Category(tenant_id=tenant.id, name=f'{name}类目', level=1)
    db.session.add(cat)
    db.session.flush()

    product = models.Product(
        tenant_id=tenant.id,
        name=product_name,
        price=product_price,
        number=100,
        introduce=f'仅属于 {slug}',
        state=2,
        cid_one=cat.id,
    )
    db.session.add(product)
    db.session.flush()

    order = models.Order(
        tenant_id=tenant.id,
        price=product_price,
        number=1,
        pay_status=1,
        address=address,
        uid=user.id,
    )
    db.session.add(order)
    print(f'   created tenant {slug} id={tenant.id} admin={admin_name} product={product_name}')
    return tenant, True


def seed(reset=False):
    with app.app_context():
        if reset:
            if os.getenv('ALLOW_DB_RESET') != '1':
                print('拒绝执行 drop_all：请设置环境变量 ALLOW_DB_RESET=1 后再加 --reset')
                print('示例：ALLOW_DB_RESET=1 python scripts/seed_tenants.py --reset')
                sys.exit(1)
            print('>> DROP ALL TABLES (ALLOW_DB_RESET=1) ...')
            db.drop_all()

        print('>> create_all ...')
        db.create_all()

        print('>> seed tenants ...')
        seed_tenant(
            slug='demo-a',
            name='演示店铺A',
            admin_name='admin_a',
            product_name='租户A专属商品-手机壳',
            product_price=19.9,
            address='上海市A区A路1号',
            phone='13800000001',
            email='a@demo.com',
        )
        seed_tenant(
            slug='demo-b',
            name='演示店铺B',
            admin_name='admin_b',
            product_name='租户B专属商品-蓝牙耳机',
            product_price=99.0,
            address='北京市B区B路2号',
            phone='13800000002',
            email='b@demo.com',
        )
        db.session.commit()

        print('>> seed done')
        print('   租户A slug=demo-a  账号=admin_a  密码=123456')
        print('   租户B slug=demo-b  账号=admin_b  密码=123456')
        print('   验收：python scripts/verify_tenant_isolation.py')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Seed multi-tenant demo data')
    parser.add_argument(
        '--reset',
        action='store_true',
        help='危险：删除当前库全部表后重建（还需 ALLOW_DB_RESET=1）',
    )
    args = parser.parse_args()
    seed(reset=args.reset)
