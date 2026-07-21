"""
种子 1～2 条演示运单（demo-a）
用法：python scripts/seed_shipments.py
"""
import os
import sys
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from flask_shop import create_app, db, models  # noqa: E402

app = create_app('develop')


def main():
    with app.app_context():
        tenant = models.Tenant.query.filter_by(slug='demo-a').first()
        if not tenant:
            print('demo-a tenant missing, run seed_tenants first')
            return
        if models.Shipment.query.filter_by(tenant_id=tenant.id).count() > 0:
            print('shipments already exist, skip')
            return
        admin = models.User.query.filter_by(tenant_id=tenant.id, name='admin_a').first()
        sh = models.Shipment(
            tenant_id=tenant.id,
            shipment_no=f'SH{tenant.id}DEMO0001',
            status='in_transit',
            customer_name='深圳某某贸易有限公司',
            customer_contact='王经理',
            customer_phone='13800001111',
            transport_mode='sea',
            origin='深圳 SHEKOU',
            destination='LOS ANGELES, US',
            incoterm='FOB',
            cargo_desc='电子配件 纸箱',
            packages=120,
            weight_kg=1800,
            volume_cbm=12.5,
            quote_amount=3200,
            currency='USD',
            bl_no='COSU1234567890',
            remark='POC 演示运单',
            owner_uid=admin.id if admin else None,
        )
        db.session.add(sh)
        db.session.flush()
        base = datetime.now() - timedelta(days=5)
        events = [
            (base, '深圳', '接到订舱委托'),
            (base + timedelta(days=1), '蛇口港', '货已入仓'),
            (base + timedelta(days=2), '蛇口港', '报关放行，已装船'),
            (base + timedelta(days=3), '太平洋', '船舶离港，运输中'),
        ]
        for t, loc, content in events:
            db.session.add(models.ShipmentEvent(
                tenant_id=tenant.id,
                shipment_id=sh.id,
                event_time=t,
                location=loc,
                content=content,
                operator_uid=admin.id if admin else None,
            ))
        db.session.commit()
        print('created', sh.shipment_no)


if __name__ == '__main__':
    main()
