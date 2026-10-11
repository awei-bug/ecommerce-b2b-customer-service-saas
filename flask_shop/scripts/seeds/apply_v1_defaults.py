# -*- coding: utf-8 -*-
"""给当前库 demo 租户套上 v1 默认付款说明（不覆盖已有非空引导时可 --force）。"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
os.environ.pop("DATABASE_URL", None)

from dotenv import load_dotenv

load_dotenv(ROOT / ".env", override=True)

from flask_shop import create_app, db, models
from flask_shop.utils.tenant_query import tenant_context

DEFAULT_PAY = """【个人收款付款说明】
1. 请使用微信或支付宝扫描下方「店铺收款码」完成转账
2. 转账金额请与订单应付金额一致
3. 备注栏请务必填写「订单号」
4. 店长核对到账后更新为已付款并安排发货
5. 有问题请联系店主（见客服电话）

说明：本店为人工确认收款，非微信/支付宝官方自动扣款。"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="强制覆盖已有 pay_guide")
    args = ap.parse_args()
    app = create_app(os.getenv("FLASK_CONFIG") or "develop")
    with app.app_context():
        with tenant_context(disabled=True):
            t = models.Tenant.query.filter_by(slug="demo").first()
            if not t:
                print("no demo tenant")
                return 1
            if args.force or not (t.pay_guide or "").strip():
                t.pay_guide = DEFAULT_PAY
                print("pay_guide set")
            else:
                print("pay_guide keep existing")
            db.session.commit()
            print("ok", t.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
