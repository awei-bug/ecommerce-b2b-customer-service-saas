"""
阶段 1 库表增量：订单状态机字段 + 支付单/退款单表。

用法（flask_shop 目录）：
  python scripts/migrations/migrate_order_payment.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from sqlalchemy import text, inspect

from manager import app  # noqa: E402
from flask_shop import db, models  # noqa: E402


def column_exists(table, column):
    insp = inspect(db.engine)
    cols = [c['name'] for c in insp.get_columns(table)]
    return column in cols


def table_exists(table):
    insp = inspect(db.engine)
    return table in insp.get_table_names()


def add_column_if_missing(table, column, ddl_type):
    if column_exists(table, column):
        print(f'  skip column {table}.{column}')
        return
    sql = f'ALTER TABLE {table} ADD COLUMN {column} {ddl_type}'
    print(f'  ADD {table}.{column} ...')
    db.session.execute(text(sql))


def migrate():
    with app.app_context():
        print('>> ensure new tables (create_all) ...')
        db.create_all()

        print('>> alter t_order columns ...')
        add_column_if_missing('t_order', 'order_no', 'VARCHAR(64) NULL')
        add_column_if_missing('t_order', 'status', "VARCHAR(32) NULL DEFAULT 'pending_pay'")
        add_column_if_missing('t_order', 'cancel_reason', 'VARCHAR(255) NULL')
        add_column_if_missing('t_order', 'paid_at', 'DATETIME NULL')
        add_column_if_missing('t_order', 'shipped_at', 'DATETIME NULL')
        add_column_if_missing('t_order', 'closed_at', 'DATETIME NULL')
        db.session.commit()

        # 尝试加索引（失败忽略）
        try:
            db.session.execute(text('CREATE INDEX ix_t_order_order_no ON t_order (order_no)'))
            db.session.commit()
        except Exception:
            db.session.rollback()
        try:
            db.session.execute(text('CREATE INDEX ix_t_order_status ON t_order (status)'))
            db.session.commit()
        except Exception:
            db.session.rollback()

        print('>> backfill order_no / status for existing rows ...')
        orders = models.Order.query.all()
        for o in orders:
            if not o.order_no:
                o.order_no = f'O{o.tenant_id}LEGACY{o.id:06d}'
            if not o.status:
                if o.is_send:
                    o.status = 'shipped'
                elif o.pay_status:
                    o.status = 'paid'
                else:
                    o.status = 'pending_pay'
        db.session.commit()
        print(f'   updated {len(orders)} orders')

        print('>> tables present:')
        for t in ('t_order', 't_payments', 't_refunds'):
            print(f'   {t}: {table_exists(t)}')
        print('>> migrate done')


if __name__ == '__main__':
    migrate()
