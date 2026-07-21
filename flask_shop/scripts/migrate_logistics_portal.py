"""create warehouse stock table"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from flask_shop import create_app, db, models  # noqa: E402

app = create_app('develop')


def main():
    with app.app_context():
        db.create_all()
        print('OK', models.WarehouseStock.__tablename__)
        # seed demo if empty for demo-a
        t = models.Tenant.query.filter_by(slug='demo-a').first()
        if t and models.WarehouseStock.query.filter_by(tenant_id=t.id).count() == 0:
            demo = [
                ('US-LAX', 'SKU-A001', '蓝牙耳机纸箱', 120, 'CTN', 'A-01-03'),
                ('US-LAX', 'SKU-B002', '手机壳混装', 80, 'CTN', 'A-02-01'),
                ('DE-HAM', 'SKU-C010', '小家电配件', 45, 'PLT', 'B-11'),
            ]
            for wh, code, name, qty, unit, loc in demo:
                db.session.add(models.WarehouseStock(
                    tenant_id=t.id, warehouse=wh, sku_code=code,
                    name=name, qty=qty, unit=unit, location=loc,
                ))
            db.session.commit()
            print('seeded warehouse demo rows')


if __name__ == '__main__':
    main()
