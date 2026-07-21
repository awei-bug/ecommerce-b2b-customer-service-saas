"""
为每个租户确保有一份默认运费模板（幂等）。
用法：python scripts/seed_freight.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from flask_shop import create_app, db, models  # noqa: E402

app = create_app('develop')


def ensure_default_freight(tenant):
    exists = models.FreightTemplate.query.filter_by(tenant_id=tenant.id).first()
    if exists:
        print(f'  skip tenant {tenant.slug}: already has freight template id={exists.id}')
        return exists, False
    row = models.FreightTemplate(
        tenant_id=tenant.id,
        name='默认运费',
        charge_type='fixed',
        fixed_fee=8.0,
        free_amount=99.0,  # 满 99 包邮
        is_default=1,
        status=1,
    )
    db.session.add(row)
    print(f'  + default freight for {tenant.slug}: fixed 8, free>=99')
    return row, True


def main():
    with app.app_context():
        db.create_all()
        tenants = models.Tenant.query.all()
        if not tenants:
            print('no tenants; run seed_tenants first')
            return
        for t in tenants:
            ensure_default_freight(t)
        db.session.commit()
        print('done')


if __name__ == '__main__':
    main()
