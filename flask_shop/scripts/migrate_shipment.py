"""
创建运单 POC 表 t_shipments / t_shipment_events
用法：
  .venv\\Scripts\\python.exe scripts\\migrate_shipment.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from flask_shop import create_app, db, models  # noqa: E402

app = create_app('develop')


def main():
    with app.app_context():
        print('create_all shipments...')
        db.create_all()
        print('OK', models.Shipment.__tablename__, models.ShipmentEvent.__tablename__)


if __name__ == '__main__':
    main()
