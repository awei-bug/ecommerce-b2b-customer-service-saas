"""
将现有员工密码重置为 pbkdf2（兼容 venv 下 OpenSSL 不支持 scrypt 的情况）。
默认重置演示账号密码为 123456。

用法：
  python scripts/reset_demo_passwords.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from flask_shop import create_app, db, models  # noqa: E402

app = create_app('develop')

# 演示账号统一重置
DEMO_NAMES = ('admin_a', 'admin_b', 'clerk', 'warehouse', 'ops', 'cs')
NEW_PWD = '123456'


def main():
    with app.app_context():
        users = models.User.query.filter(models.User.name.in_(DEMO_NAMES)).all()
        if not users:
            print('no demo users found')
            return
        for u in users:
            u.password = NEW_PWD
            print(f'  reset {u.name} tenant_id={u.tenant_id}')
        db.session.commit()
        print(f'done: {len(users)} users -> password={NEW_PWD} (pbkdf2)')


if __name__ == '__main__':
    main()
