"""创建 t_warehouse_stocks + 演示库存"""
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
        # seed demo for each tenant if empty
        for t in models.Tenant.query.all():
            n = models.WarehouseStock.query.filter_by(tenant_id=t.id).count()
            if n:
                print(f'  tenant {t.slug} stocks={n} skip seed')
                continue
            samples = [
                ('US-LAX', 'SKU-PHONE-CASE', '手机壳-混色', 320, 'CTN', 'A-01-12'),
                ('US-LAX', 'SKU-EARBUD', '蓝牙耳机', 85, 'CTN', 'A-02-03'),
                ('DE-HAM', 'SKU-BAG', '帆布袋', 140, 'CTN', 'B-01-01'),
            ]
            for wh, code, name, qty, unit, loc in samples:
                db.session.add(models.WarehouseStock(
                    tenant_id=t.id,
                    warehouse=wh,
                    sku_code=code,
                    name=name,
                    qty=qty,
                    unit=unit,
                    location=loc,
                ))
            print(f'  tenant {t.slug} seeded {len(samples)} stocks')
        db.session.commit()
        print('done')


if __name__ == '__main__':
    main()
