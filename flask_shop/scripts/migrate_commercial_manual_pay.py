"""
商用私有化：租户付款指引字段。
用法：.venv\\Scripts\\python scripts/migrate_commercial_manual_pay.py
"""
import os
import sys

from sqlalchemy import text

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from flask_shop import create_app, db, models  # noqa: E402

app = create_app('develop')

DEFAULT_GUIDE = (
    '下单后请按本店说明完成付款（微信/支付宝转账等）。\n'
    '付款时备注订单号，商家确认到账后会将订单更新为「已付款」并安排发货。\n'
    '本系统当前不支持在线自动扣款，订单支付状态由商家人工确认。'
)


def column_exists(table, column):
    rows = db.session.execute(text(f'SHOW COLUMNS FROM {table}')).fetchall()
    names = {r[0] for r in rows}
    return column in names


def add_col(table, column, ddl):
    if column_exists(table, column):
        print(f'skip {table}.{column}')
        return
    db.session.execute(text(f'ALTER TABLE {table} ADD COLUMN {ddl}'))
    print(f'ADD {table}.{column}')


def main():
    with app.app_context():
        db.create_all()
        add_col('t_tenants', 'pay_guide', 'pay_guide TEXT NULL')
        add_col('t_tenants', 'contact_phone', 'contact_phone VARCHAR(32) NULL')
        db.session.commit()

        # 给空指引的租户填默认文案
        for t in models.Tenant.query.all():
            if not t.pay_guide:
                t.pay_guide = DEFAULT_GUIDE
                print(f'set default pay_guide tenant={t.slug}')
        db.session.commit()
        print('done')


if __name__ == '__main__':
    main()
