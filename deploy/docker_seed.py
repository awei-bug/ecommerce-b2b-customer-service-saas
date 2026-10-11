# run inside shop_api container
import os, sys, json
sys.path.insert(0, "/app")
os.environ.setdefault("FLASK_CONFIG", os.getenv("FLASK_CONFIG") or "sample")

from flask_shop import create_app, db, models
from flask_shop.utils.tenant_query import tenant_context
from flask_shop.utils.rbac import ROLE_TEMPLATES, ALL_ACTION_CODES
import json as _json

app = create_app(os.environ["FLASK_CONFIG"])

DEFAULT_PAY = (
    "【付款说明】\n"
    "1. 下单后请按本店约定方式转账（微信/支付宝等）\n"
    "2. 转账备注务必填写订单号\n"
    "3. 店长核对到账后安排发货\n"
    "（订单支付状态由商家人工确认，非自动扣款）"
)

MENU_L1 = [
    ('用户管理', 'users'),
    ('权限管理', 'rights'),
    ('商品管理', 'goods'),
    ('订单管理', 'orders'),
    ('数据统计', 'reports'),
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
    ('店铺设置', 'shop_settings', '店铺设置'),
]

PRODUCTS = [
    ("无线降噪耳机 Pro", 599.0, 80, "数码家电", "主动降噪，续航 30 小时"),
    ("机械键盘青轴", 299.0, 120, "数码家电", "热插拔轴体，RGB 灯效"),
    ("纯棉基础 T 恤", 89.0, 200, "服饰鞋包", "100% 新疆棉"),
    ("真皮通勤托特包", 459.0, 45, "服饰鞋包", "头层牛皮，大容量"),
    ("精品挂耳咖啡 20 杯", 68.0, 300, "食品生鲜", "中浅烘焙"),
    ("北欧原木台灯", 189.0, 60, "家居生活", "三档调光"),
    ("记忆棉颈椎枕", 129.0, 90, "家居生活", "慢回弹"),
    ("智能手环 S7", 249.0, 150, "数码家电", "血氧心率"),
]

def main():
    with app.app_context():
        db.create_all()
        with tenant_context(disabled=True):
            # menus
            menus = {}
            all_menus = []
            for name, path in MENU_L1:
                m = models.Menu.query.filter_by(name=name, level=1).first()
                if not m:
                    m = models.Menu(name=name, path=path, level=1)
                    db.session.add(m)
                    db.session.flush()
                menus[name] = m
                all_menus.append(m)
            for name, path, parent in MENU_L2:
                m = models.Menu.query.filter_by(name=name, path=path).first()
                if not m:
                    m = models.Menu(name=name, path=path, level=2, pid=menus[parent].id)
                    db.session.add(m)
                    db.session.flush()
                all_menus.append(m)

            t = models.Tenant.query.filter_by(slug="demo").first()
            if not t:
                t = models.Tenant(
                    name="云购演示旗舰店",
                    slug="demo",
                    status=1,
                    plan_code="pro",
                    contact_phone="400-800-1234",
                    pay_guide=DEFAULT_PAY,
                    theme="retail",
                )
                db.session.add(t)
                db.session.flush()
                print("+ tenant demo")
            else:
                t.pay_guide = t.pay_guide or DEFAULT_PAY
                if hasattr(t, "theme") and not t.theme:
                    t.theme = "retail"
                print("~ tenant demo")

            role = models.Role.query.filter_by(tenant_id=t.id, name="超级管理员").first()
            if not role:
                role = models.Role(tenant_id=t.id, name="超级管理员", desc="全部权限")
                if hasattr(role, "is_super"):
                    role.is_super = 1
                db.session.add(role)
                db.session.flush()
            role.menus = list(all_menus)
            if hasattr(role, "is_super"):
                role.is_super = 1
            if hasattr(role, "perm_codes"):
                role.perm_codes = _json.dumps(ALL_ACTION_CODES, ensure_ascii=False)

            admin = models.User.query.filter_by(tenant_id=t.id, name="admin").first()
            if not admin:
                admin = models.User(tenant_id=t.id, name="admin", nick_name="店长", phone="13800000000", role_id=role.id, is_admin=1)
                admin.password = "123456"
                db.session.add(admin)
                print("+ admin/123456")
            else:
                admin.role_id = role.id
                admin.is_admin = 1
                admin.password = "123456"
                print("~ admin reset 123456")

            cats = {}
            for cname in ["数码家电", "服饰鞋包", "食品生鲜", "家居生活"]:
                c = models.Category.query.filter_by(tenant_id=t.id, name=cname, level=1).first()
                if not c:
                    c = models.Category(tenant_id=t.id, name=cname, level=1)
                    db.session.add(c)
                    db.session.flush()
                cats[cname] = c

            created = 0
            for name, price, stock, cat, intro in PRODUCTS:
                if models.Product.query.filter_by(tenant_id=t.id, name=name).first():
                    continue
                p = models.Product(
                    tenant_id=t.id, name=name, price=price, number=stock,
                    introduce=intro, state=2, cid_one=cats[cat].id, hot_number=stock // 3,
                )
                db.session.add(p)
                created += 1
            print("+ products", created)

            if not models.FreightTemplate.query.filter_by(tenant_id=t.id).first():
                db.session.add(models.FreightTemplate(
                    tenant_id=t.id, name="默认运费", charge_type="fixed",
                    fixed_fee=8.0, free_amount=99.0, is_default=1, status=1,
                ))
                print("+ freight")

            db.session.commit()
            print("SEED_OK products=", models.Product.query.filter_by(tenant_id=t.id).count())

if __name__ == "__main__":
    main()