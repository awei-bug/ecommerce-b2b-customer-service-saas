"""
创建审计表等缺失表（create_all 增量）。
用法：python scripts/migrations/migrate_l0_ops.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from manager import app  # noqa: E402
from flask_shop import db, models  # noqa: E402


def migrate():
    with app.app_context():
        db.create_all()
        print('create_all done')
        print('AuditLog table:', models.AuditLog.__tablename__)


if __name__ == '__main__':
    migrate()
