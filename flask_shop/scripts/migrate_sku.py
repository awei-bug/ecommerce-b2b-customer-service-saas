"""
创建 t_product_skus，订单明细增加 sku_id/sku_label。
用法：
  .venv\\Scripts\\python.exe scripts\\migrate_sku.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from sqlalchemy import inspect, text

from flask_shop import create_app, db, models  # noqa: E402

app = create_app('develop')


def has_column(table, col):
    insp = inspect(db.engine)
    if table not in insp.get_table_names():
        return False
    return any(c['name'] == col for c in insp.get_columns(table))


def main():
    with app.app_context():
        print('create_all (sku table)...')
        db.create_all()
        # order detail columns
        if not has_column('t_order_detail', 'sku_id'):
            print('ADD t_order_detail.sku_id')
            db.session.execute(text(
                'ALTER TABLE t_order_detail ADD COLUMN sku_id INT NULL'
            ))
        if not has_column('t_order_detail', 'sku_label'):
            print('ADD t_order_detail.sku_label')
            db.session.execute(text(
                "ALTER TABLE t_order_detail ADD COLUMN sku_label VARCHAR(128) NULL"
            ))
        db.session.commit()
        print('ProductSku table:', models.ProductSku.__tablename__)
        print('done')


if __name__ == '__main__':
    main()
