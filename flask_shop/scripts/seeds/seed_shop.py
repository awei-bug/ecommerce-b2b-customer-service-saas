# -*- coding: utf-8 -*-
"""初始化电商演示数据。

用法:
  set ALLOW_DB_RESET=1
  .venv\\Scripts\\python scripts\\seeds\\seed_shop.py --reset
"""
import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from flask_shop import create_app, db, models

app = create_app('develop')

DEFAULT_PAY_GUIDE = (
    '【个人收款付款说明】\n'
    '1. 请扫码微信/支付宝个人收款码完成转账\n'
    '2. 金额与订单一致\n'
    '3. 备注栏务必填写订单号\n'
    '4. 店长确认到账后发货（非官方自动扣款）'
)

MENU_L1 = [
    ('用户管理', 'users'),
    ('权限管理', 'rights'),
    ('商品管理', 'goods'),
    ('订单管理', 'orders'),
    ('数据统计', 'reports'),
    ('客服中心', 'service'),
    ('店铺设置', 'shop'),
]

MENU_L2 = [
    ('用户列表', 'user_list', '用户管理'),
    ('角色列表', 'role_list', '权限管理'),
    ('权限分配', 'author_list', '权限管理'),
    ('动作权限', 'role_actions', '权限管理'),
    ('商品列表', 'product_list', '商品管理'),
    ('添加商品', 'add_product', '商品管理'),
    ('分类参数', 'attribute_list', '商品管理'),
    ('商品分类', 'group_list', '商品管理'),
    ('运费模板', 'freight', '商品管理'),
    ('订单列表', 'order_list', '订单管理'),
    ('数据报表', 'data_list', '数据统计'),
    ('客服工作台', 'customer_service', '客服中心'),
    ('店铺设置', 'shop_settings', '店铺设置'),
]


def ensure_menus():
    menus = {}
    for name, path in MENU_L1:
        m = models.Menu.query.filter_by(name=name, level=1).first()
        if not m:
            m = models.Menu(name=name, path=path, level=1)
            db.session.add(m)
            db.session.flush()
        menus[name] = m
    all_menus = list(menus.values())
    for name, path, parent_name in MENU_L2:
        m = models.Menu.query.filter_by(name=name, path=path).first()
        if not m:
            m = models.Menu(name=name, path=path, level=2, pid=menus[parent_name].id)
            db.session.add(m)
            db.session.flush()
        all_menus.append(m)
    return all_menus


def seed_shop(reset=False):
    with app.app_context():
        if reset:
            if os.getenv('ALLOW_DB_RESET') != '1':
                print('拒绝 drop_all：请设置 ALLOW_DB_RESET=1')
                sys.exit(1)
            print('>> drop_all ...')
            db.drop_all()

        print('>> create_all ...')
        db.create_all()
        menus = ensure_menus()

        tenant = models.Tenant.query.filter_by(slug='demo').first()
        if not tenant:
            tenant = models.Tenant(
                name='云购演示旗舰店',
                slug='demo',
                status=1,
                plan_code='pro',
                data_mode='demo',
                contact_phone='400-800-1234',
                pay_guide=DEFAULT_PAY_GUIDE,
            )
            db.session.add(tenant)
            db.session.flush()
            print('  + tenant demo')
        else:
            tenant.name = '云购演示旗舰店'
            tenant.data_mode = 'demo'
            tenant.pay_guide = tenant.pay_guide or DEFAULT_PAY_GUIDE
            print('  ~ tenant demo')

        role = models.Role.query.filter_by(tenant_id=tenant.id, name='超级管理员').first()
        if not role:
            role = models.Role(tenant_id=tenant.id, name='超级管理员', desc='全部权限', is_super=1)
            db.session.add(role)
            db.session.flush()
        role.menus = list(menus)
        role.is_super = 1

        admin = models.User.query.filter_by(tenant_id=tenant.id, name='admin').first()
        if not admin:
            admin = models.User(
                tenant_id=tenant.id,
                name='admin',
                nick_name='店长',
                phone='13800000000',
                email='admin@demo.shop',
                role_id=role.id,
                is_admin=1,
            )
            admin.password = '123456'
            db.session.add(admin)
            print('  + admin/123456')
        else:
            admin.role_id = role.id
            admin.is_admin = 1
            admin.password = '123456'
            print('  ~ admin password reset to 123456')

        # 分类
        cats = {}
        for cname in ['数码家电', '服饰鞋包', '食品生鲜', '家居生活']:
            c = models.Category.query.filter_by(tenant_id=tenant.id, name=cname, level=1).first()
            if not c:
                c = models.Category(tenant_id=tenant.id, name=cname, level=1)
                db.session.add(c)
                db.session.flush()
            cats[cname] = c

        products = [
            ('无线降噪耳机 Pro', 599.0, 80, '数码家电', '主动降噪，续航 30 小时，蓝牙 5.3'),
            ('机械键盘青轴', 299.0, 120, '数码家电', '热插拔轴体，RGB 灯效'),
            ('纯棉基础 T 恤', 89.0, 200, '服饰鞋包', '100% 新疆棉，多色可选'),
            ('真皮通勤托特包', 459.0, 45, '服饰鞋包', '头层牛皮，大容量'),
            ('精品挂耳咖啡 20 杯', 68.0, 300, '食品生鲜', '中浅烘焙，花香果酸'),
            ('北欧原木台灯', 189.0, 60, '家居生活', '三档调光，护眼暖光'),
            ('记忆棉颈椎枕', 129.0, 90, '家居生活', '慢回弹，可水洗外套'),
            ('智能手环 S7', 249.0, 150, '数码家电', '血氧心率，14 天续航'),
        ]
        created = 0
        for name, price, stock, cat, intro in products:
            exists = models.Product.query.filter_by(tenant_id=tenant.id, name=name).first()
            if exists:
                continue
            p = models.Product(
                tenant_id=tenant.id,
                name=name,
                price=price,
                number=stock,
                introduce=intro,
                state=2,
                cid_one=cats[cat].id,
                hot_number=stock // 3,
            )
            db.session.add(p)
            created += 1
        print(f'  + products {created}')

        # 给耳机加 SKU 示例
        ear = models.Product.query.filter_by(tenant_id=tenant.id, name='无线降噪耳机 Pro').first()
        if ear and ear.skus.count() == 0:
            for color, stock in [('黑色', 30), ('白色', 25), ('银色', 25)]:
                db.session.add(models.ProductSku(
                    tenant_id=tenant.id,
                    product_id=ear.id,
                    sku_code=f'EAR-{color}',
                    specs=__import__('json').dumps({'颜色': color}, ensure_ascii=False),
                    price=599.0,
                    stock=stock,
                    status=1,
                ))
            ear.number = 0
            print('  + earphone SKUs')

        # 运费
        if not models.FreightTemplate.query.filter_by(tenant_id=tenant.id).first():
            db.session.add(models.FreightTemplate(
                tenant_id=tenant.id,
                name='默认运费',
                charge_type='fixed',
                fixed_fee=8.0,
                free_amount=99.0,
                is_default=1,
                status=1,
            ))
            print('  + freight template')

        db.session.commit()
        print('>> done')
        print('商家后台: tenant=demo  admin / 123456')
        print('顾客端:   tenant=demo  手机任意合法号 + 验证码 123456')


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--reset', action='store_true')
    args = p.parse_args()
    seed_shop(reset=args.reset)
