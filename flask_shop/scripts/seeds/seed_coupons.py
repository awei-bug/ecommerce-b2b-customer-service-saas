# -*- coding: utf-8 -*-
"""初始化演示优惠券。"""
from __future__ import annotations
import os, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
os.environ.pop("DATABASE_URL", None)
from dotenv import load_dotenv
load_dotenv(ROOT / ".env", override=True)
from flask_shop import create_app, db, models
from flask_shop.utils.tenant_query import tenant_context

DEFAULTS = [
    {"name": "满99包邮", "coupon_type": "shipping_free", "threshold": 99, "amount_off": 0, "note": "实付满99免运费（示意，需运费模板配合）"},
    {"name": "满199减20", "coupon_type": "amount_off", "threshold": 199, "amount_off": 20, "note": "满减活动"},
]

def main():
    app = create_app(os.getenv("FLASK_CONFIG") or "develop")
    with app.app_context():
        db.create_all()
        with tenant_context(disabled=True):
            t = models.Tenant.query.filter_by(slug="demo").first()
            if not t:
                print("no demo"); return 1
            n = 0
            for d in DEFAULTS:
                exists = models.Coupon.query.filter_by(tenant_id=t.id, name=d["name"]).first()
                if exists:
                    continue
                db.session.add(models.Coupon(tenant_id=t.id, status=1, **d))
                n += 1
            db.session.commit()
            print("coupons_added", n, "total", models.Coupon.query.filter_by(tenant_id=t.id).count())
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
