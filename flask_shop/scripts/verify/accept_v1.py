# -*- coding: utf-8 -*-
"""v1 技术验收：代客下单 → 确认收款 → 发货 → 顾客可见物流。

用法（开发库）:
  .venv\\Scripts\\python scripts\\verify\\accept_v1.py

可选环境:
  ACCEPT_BASE=http://127.0.0.1:5000  对已启动服务验收（未实现，默认 in-process）
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
os.environ.setdefault("FLASK_CONFIG", "develop")
os.environ.setdefault("SMS_DEV_MODE", "1")
os.environ.setdefault("ALLOW_MOCK_PAY", "1")

from flask_shop import create_app, models
from flask_shop.utils.tenant_query import tenant_context


def main():
    app = create_app("develop")
    c = app.test_client()
    fails = []

    def check(name, cond, detail=""):
        if cond:
            print(f"[OK] {name} {detail}")
        else:
            print(f"[FAIL] {name} {detail}")
            fails.append(name)

    # merchant login
    rv = c.post("/user/login/", json={"name": "admin", "pwd": "123456", "tenant_slug": "demo"})
    body = rv.get_json() or {}
    check("店长登录", body.get("status") == 200, body.get("msg"))
    token = (body.get("data") or {}).get("token")
    MH = {"token": token}

    # pick product with stock no sku preferred
    with app.app_context():
        with tenant_context(disabled=True):
            pid = None
            for p in models.Product.query.filter(models.Product.number > 0).all():
                if p.skus.count() == 0:
                    pid = p.id
                    break
            if pid is None:
                p = models.Product.query.filter(models.Product.number > 0).first()
                pid = p.id if p else None
    check("有可售商品", bool(pid), f"pid={pid}")

    # proxy order
    phone = "13700006666"
    rv = c.post(
        "/orders/",
        json={
            "customer_phone": phone,
            "customer_nickname": "验收客户",
            "contact_name": "验收客户",
            "address": "广东省深圳市南山区验收路 1 号",
            "items": [{"pid": pid, "number": 1}],
        },
        headers=MH,
    )
    body = rv.get_json() or {}
    check("代客下单", body.get("status") == 200, body.get("msg"))
    order = body.get("data") or {}
    oid = order.get("id")
    check("订单待支付", order.get("status") == "pending_pay", order.get("status"))
    check("绑定买家", bool(order.get("customer_id")), str(order.get("customer_id")))

    rv = c.post(f"/order/{oid}/mark-paid/", json={"note": "验收转账"}, headers=MH)
    body = rv.get_json() or {}
    check("确认收款", body.get("status") == 200 and (body.get("data") or {}).get("order", {}).get("status") == "paid")

    rv = c.post(f"/order/{oid}/ship/", json={"content": "验收快递 YZ001"}, headers=MH)
    body = rv.get_json() or {}
    check("发货", body.get("status") == 200 and (body.get("data") or {}).get("status") == "shipped")

    # customer login see order
    H = {"X-Tenant-Slug": "demo"}
    rv = c.post("/api/c/auth/sms/send/", json={"phone": phone}, headers=H)
    code = ((rv.get_json() or {}).get("data") or {}).get("dev_code")
    rv = c.post("/api/c/auth/sms/login/", json={"phone": phone, "code": code}, headers=H)
    ctoken = ((rv.get_json() or {}).get("data") or {}).get("token")
    check("顾客登录", bool(ctoken))
    rv = c.get(f"/api/c/order/{oid}/", headers={**H, "token": ctoken})
    data = (rv.get_json() or {}).get("data") or {}
    check("顾客见发货", data.get("status") == "shipped", data.get("status"))
    check("顾客见物流", bool(data.get("express")), str(data.get("express")))

    print("========")
    if fails:
        print("ACCEPT_FAIL", fails)
        sys.exit(1)
    print("ACCEPT_V1_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main() or 0)
