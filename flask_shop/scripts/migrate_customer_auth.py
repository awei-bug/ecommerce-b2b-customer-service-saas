"""
Customer 相关表 + order.customer_id 增量迁移。

用法：
  cd flask_shop
  python scripts/migrate_customer_auth.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from sqlalchemy import text, inspect

from manager import app  # noqa: E402
from flask_shop import db  # noqa: E402


def column_exists(table, column):
    insp = inspect(db.engine)
    if table not in insp.get_table_names():
        return False
    return column in [c['name'] for c in insp.get_columns(table)]


def migrate():
    with app.app_context():
        print('>> create_all (customers / addresses / sms_codes) ...')
        db.create_all()

        if not column_exists('t_order', 'customer_id'):
            print('>> ADD t_order.customer_id')
            db.session.execute(text(
                'ALTER TABLE t_order ADD COLUMN customer_id INT NULL'
            ))
            db.session.commit()
            try:
                db.session.execute(text(
                    'CREATE INDEX ix_t_order_customer_id ON t_order (customer_id)'
                ))
                db.session.commit()
            except Exception:
                db.session.rollback()
        else:
            print('>> skip t_order.customer_id')

        print('>> done')
        insp = inspect(db.engine)
        for t in ('t_customers', 't_customer_addresses', 't_sms_codes'):
            print(f'   {t}: {t in insp.get_table_names()}')


if __name__ == '__main__':
    migrate()
