"""
L1 增量：运费模板表 + 订单金额字段。
用法：.venv\\Scripts\\python scripts/migrations/migrate_l1_features.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from sqlalchemy import text, inspect

from manager import app  # noqa: E402
from flask_shop import db, models  # noqa: E402


def has_col(table, col):
    insp = inspect(db.engine)
    if table not in insp.get_table_names():
        return False
    return col in [c['name'] for c in insp.get_columns(table)]


def migrate():
    with app.app_context():
        print('create_all...')
        db.create_all()

        alters = [
            ('t_order', 'goods_amount', 'DOUBLE NULL'),
            ('t_order', 'freight_amount', 'DOUBLE NULL DEFAULT 0'),
            ('t_order', 'freight_template_id', 'INT NULL'),
        ]
        for table, col, ddl in alters:
            if has_col(table, col):
                print('skip', table, col)
            else:
                print('ADD', table, col)
                db.session.execute(text(f'ALTER TABLE {table} ADD COLUMN {col} {ddl}'))
                db.session.commit()

        # 回填 goods_amount
        db.session.execute(text(
            'UPDATE t_order SET goods_amount = price WHERE goods_amount IS NULL'
        ))
        db.session.execute(text(
            'UPDATE t_order SET freight_amount = 0 WHERE freight_amount IS NULL'
        ))
        db.session.commit()

        print('FreightTemplate:', models.FreightTemplate.__tablename__)
        print('done')


if __name__ == '__main__':
    migrate()
