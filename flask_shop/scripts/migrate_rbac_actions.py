"""
为 t_roles 增加 perm_codes 字段（动作级 RBAC）。
用法：python scripts/migrate_rbac_actions.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from sqlalchemy import text, inspect

from manager import app  # noqa: E402
from flask_shop import db  # noqa: E402


def migrate():
    with app.app_context():
        insp = inspect(db.engine)
        cols = [c['name'] for c in insp.get_columns('t_roles')]
        if 'perm_codes' not in cols:
            print('ADD t_roles.perm_codes TEXT')
            db.session.execute(text('ALTER TABLE t_roles ADD COLUMN perm_codes TEXT NULL'))
            db.session.commit()
        else:
            print('skip perm_codes exists')
        print('done')


if __name__ == '__main__':
    migrate()
