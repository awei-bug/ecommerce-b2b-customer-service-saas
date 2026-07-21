"""
动作级 RBAC 角色模板种子。

为每个活跃租户确保：
  - 店员 / 仓管 / 运营 / 客服 角色（含 menu + perm_codes）
  - 可选账号：
      clerk / 123456   店员
      warehouse / 123456 仓管
      ops / 123456     运营
      cs / 123456      客服

用法：
  python scripts/seed_rbac_roles.py
  python scripts/seed_rbac_roles.py --with-users
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from flask_shop import create_app, db, models  # noqa: E402
from flask_shop.utils.rbac import ROLE_TEMPLATES  # noqa: E402

app = create_app('develop')

USER_SPECS = {
    '店员': ('clerk', '13900000091', '店员'),
    '仓管': ('warehouse', '13900000092', '仓管'),
    '运营': ('ops', '13900000093', '运营'),
    '客服': ('cs', '13900000094', '客服'),
}


def menus_for_paths(paths):
    menus = models.Menu.query.filter(models.Menu.path.in_(list(paths))).all()
    parent_ids = {m.pid for m in menus if m.pid}
    parents = models.Menu.query.filter(models.Menu.id.in_(parent_ids)).all() if parent_ids else []
    return list({m.id: m for m in (list(menus) + list(parents))}.values())


def ensure_role(tenant, role_name, template):
    role = models.Role.query.filter_by(tenant_id=tenant.id, name=role_name).first()
    if not role:
        role = models.Role(tenant_id=tenant.id, name=role_name, desc=template['desc'])
        db.session.add(role)
        db.session.flush()
        print(f'  + role {role_name} @ {tenant.slug}')
    else:
        role.desc = template['desc']
        print(f'  ~ role {role_name} @ {tenant.slug}')
    role.menus = menus_for_paths(template['menu_paths'])
    role.perm_codes = json.dumps(template['perm_codes'], ensure_ascii=False)
    return role


def ensure_user(tenant, role, username, phone, nick):
    user = models.User.query.filter_by(tenant_id=tenant.id, name=username).first()
    if user:
        user.role_id = role.id
        print(f'  ~ user {username} role={role.name}')
        return user
    user = models.User(
        tenant_id=tenant.id,
        name=username,
        nick_name=f'{tenant.name}{nick}',
        phone=phone,
        email=f'{username}@{tenant.slug}.demo',
        role_id=role.id,
    )
    user.password = '123456'
    db.session.add(user)
    print(f'  + user {username}/123456 role={role.name}')
    return user


def main(with_users=False):
    with app.app_context():
        # 确保列存在
        try:
            from sqlalchemy import text, inspect
            cols = [c['name'] for c in inspect(db.engine).get_columns('t_roles')]
            if 'perm_codes' not in cols:
                db.session.execute(text('ALTER TABLE t_roles ADD COLUMN perm_codes TEXT NULL'))
                db.session.commit()
                print('added perm_codes column')
        except Exception as e:
            print('migrate note', e)
            db.session.rollback()

        tenants = models.Tenant.query.filter_by(status=1).all()
        if not tenants:
            print('no tenants')
            return
        for t in tenants:
            print('tenant', t.slug)
            for role_name, tpl in ROLE_TEMPLATES.items():
                role = ensure_role(t, role_name, tpl)
                if with_users and role_name in USER_SPECS:
                    u, phone, nick = USER_SPECS[role_name]
                    ensure_user(t, role, u, phone, nick)
        db.session.commit()
        print('done')
        if with_users:
            print('账号：clerk/warehouse/ops/cs  密码均为 123456  租户 demo-a')


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--with-users', action='store_true')
    p.add_argument('--with-clerk', action='store_true', help='兼容旧参数，等同 --with-users')
    args = p.parse_args()
    main(with_users=args.with_users or args.with_clerk)
