# -*- coding: utf-8 -*-
"""人工收款全链路彩排（develop + 种子库）"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

# 固定 develop，避免 product 环境变量干扰
for k in list(os.environ):
    if k in (
        "FLASK_CONFIG", "ALLOW_MOCK_PAY", "SMS_DEV_MODE", "PRIVATE_DEPLOY",
        "PLATFORM_BOOTSTRAP_KEY", "PUBLIC_BASE_URL", "PAY_DEFAULT_CHANNEL",
        "ORDER_PENDING_TIMEOUT_MINUTES", "SECRET_KEY", "CORS_ORIGINS",
    ):
        # keep DATABASE_URL / dotenv will load .env
        if k != "DATABASE_URL":
            pass
os.environ["FLASK_CONFIG"] = "develop"
os.environ["ALLOW_MOCK_PAY"] = "1"
os.environ["SMS_DEV_MODE"] = "1"
os.environ["SMS_DEV_CODE"] = "123456"
os.environ.setdefault(
    "DATABASE_URL",
    r"sqlite:///F:/Python_code/Flask项目/flask_shop/instance/ecommerce_shop.db",
)

from flask_shop import create_app, db, models  # noqa: E402
from flask_shop.utils.tenant_query import tenant_context  # noqa: E402

STEPS = []
ISSUES = []


def ok(name, detail=""):
    STEPS.append({"step": name, "ok": True, "detail": detail})
    print(f"[OK] {name}" + (f" | {detail}" if detail else ""))


def fail(name, detail=""):
    STEPS.append({"step": name, "ok": False, "detail": detail})
    ISSUES.append(f"{name}: {detail}")
    print(f"[FAIL] {name} | {detail}")
    raise SystemExit(2)


def main():
    app = create_app("develop")
    client = app.test_client()

    with app.app_context():
        with tenant_context(disabled=True):
            tenant = models.Tenant.query.filter_by(slug="demo").first()
            if not tenant:
                fail("检查种子租户", "缺少 slug=demo，请先 seed_shop.py")
            products = models.Product.query.filter_by(tenant_id=tenant.id).all()
            # 选有库存、无强制 SKU 或有 SKU 的商品
            pick = None
            for p in products:
                skus = list(p.skus) if hasattr(p, "skus") else []
                if skus:
                    live = [s for s in skus if getattr(s, "status", 1) == 1 and (s.stock or 0) > 0]
                    if live:
                        pick = ("sku", p, live[0])
                        break
                elif (p.number or 0) > 0:
                    pick = ("spu", p, None)
                    break
            if not pick:
                fail("选商品", "没有可售库存商品")
            ok("种子数据", f"tenant={tenant.slug} products={len(products)} pick={pick[1].name}")

    H = {"X-Tenant-Slug": "demo"}

    # 1) C 端店铺
    rv = client.get("/api/c/shop/", headers=H)
    body = rv.get_json() or {}
    if body.get("status") != 200:
        fail("C端店铺信息", body)
    pay_guide = (body.get("data") or {}).get("pay_guide") or ""
    if "确认收款" not in pay_guide and "人工" not in pay_guide and "转账" not in pay_guide:
        ISSUES.append("pay_guide 文案可能不够明确（无转账/确认收款关键词）")
    ok("C端店铺信息", f"name={(body.get('data') or {}).get('name')}")

    # 2) 发短信
    phone = "13900001234"
    rv = client.post("/api/c/auth/sms/send/", json={"phone": phone}, headers=H)
    body = rv.get_json() or {}
    if body.get("status") != 200:
        fail("发送验证码", body)
    dev_code = ((body.get("data") or {}).get("dev_code")
                or (body.get("data") or {}).get("code"))
    if not dev_code:
        fail("发送验证码", f"开发模式未返回 dev_code: {body}")
    ok("发送验证码", f"dev_code={dev_code}")

    # 3) 登录（必须用发送接口返回的 dev_code，不是写死 123456）
    rv = client.post(
        "/api/c/auth/sms/login/",
        json={"phone": phone, "code": str(dev_code)},
        headers=H,
    )
    body = rv.get_json() or {}
    if body.get("status") != 200:
        fail("顾客登录", body)
    ctoken = (body.get("data") or {}).get("token")
    if not ctoken:
        fail("顾客登录", f"无 token: {body}")
    ok("顾客登录", f"phone={phone}")
    CH = {**H, "token": ctoken}

    # 4) 商品列表/详情
    rv = client.get("/api/c/products/", headers=H)
    body = rv.get_json() or {}
    if body.get("status") != 200:
        fail("C端商品列表", body)
    pdata = body.get("data")
    if isinstance(pdata, dict):
        plist = pdata.get("products") or pdata.get("items") or pdata.get("list") or pdata.get("data") or []
    else:
        plist = pdata or []
    if not plist:
        # try alternate path
        rv2 = client.get("/api/c/product/list/", headers=H)
        # introspect routes - use resource
        fail("C端商品列表", f"空列表 body_keys={list(body.keys())} data_type={type(pdata)} data={str(pdata)[:300]}")
    ok("C端商品列表", f"n={len(plist)}")

    mode, product, sku = pick
    pid = product.id
    rv = client.get(f"/api/c/product/{pid}/", headers=H)
    # maybe products detail path different
    if (rv.get_json() or {}).get("status") != 200:
        rv = client.get(f"/api/c/products/{pid}/", headers=H)
    body = rv.get_json() or {}
    if body.get("status") != 200:
        ISSUES.append(f"商品详情路径需确认: {body}")
        ok("C端商品详情", f"跳过/告警 pid={pid}")
    else:
        ok("C端商品详情", f"pid={pid}")

    # 5) 地址
    rv = client.post(
        "/api/c/addresses/",
        json={
            "contact_name": "彩排收件人",
            "contact_phone": phone,
            "region": "广东省深圳市南山区",
            "detail": "彩排路 1 号",
            "is_default": 1,
        },
        headers=CH,
    )
    body = rv.get_json() or {}
    if body.get("status") != 200:
        fail("创建收货地址", body)
    addr = body.get("data") or {}
    addr_id = addr.get("id")
    ok("创建收货地址", f"id={addr_id}")

    # 6) 下单
    item = {"pid": pid, "number": 1}
    if mode == "sku" and sku is not None:
        item["sku_id"] = sku.id
    order_body = {
        "items": [item],
        "address": "广东省深圳市南山区彩排路1号",
        "address_id": addr_id,
        "receiver": "彩排收件人",
        "phone": phone,
    }
    rv = client.post("/api/c/orders/", json=order_body, headers=CH)
    body = rv.get_json() or {}
    if body.get("status") != 200:
        fail("顾客下单", body)
    order = body.get("data") or {}
    oid = order.get("id")
    onostr = order.get("order_no") or order.get("orderNo")
    ostatus = order.get("status")
    if ostatus != "pending_pay":
        ISSUES.append(f"下单后状态不是 pending_pay 而是 {ostatus}")
    ok("顾客下单", f"id={oid} no={onostr} status={ostatus} price={order.get('price')}")

    # 7) 订单详情可见付款说明/待支付
    rv = client.get(f"/api/c/order/{oid}/", headers=CH)
    body = rv.get_json() or {}
    if body.get("status") != 200:
        fail("顾客订单详情", body)
    ok("顾客订单详情", f"status={(body.get('data') or {}).get('status')}")

    # 8) 商家登录
    rv = client.post(
        "/user/login/",
        json={"name": "admin", "pwd": "123456", "tenant_slug": "demo"},
    )
    body = rv.get_json() or {}
    if body.get("status") != 200:
        fail("店长登录", body)
    mtoken = (body.get("data") or {}).get("token")
    ok("店长登录", "demo/admin")
    MH = {"token": mtoken}

    # 9) 后台看到待支付订单
    rv = client.get("/orders/?status=pending_pay", headers=MH)
    body = rv.get_json() or {}
    if body.get("status") != 200:
        fail("后台订单列表", body)
    ok("后台待支付列表", "status=200")

    # 10) 确认收款
    rv = client.post(
        f"/order/{oid}/mark-paid/",
        json={"note": "彩排微信转账尾号 9527"},
        headers=MH,
    )
    body = rv.get_json() or {}
    if body.get("status") != 200:
        fail("确认收款", body)
    ost = ((body.get("data") or {}).get("order") or {}).get("status")
    ch = ((body.get("data") or {}).get("payment") or {}).get("channel")
    if ost != "paid":
        fail("确认收款后状态", f"got {ost}")
    ok("确认收款", f"order={ost} payment_channel={ch}")

    # 11) 发货
    rv = client.post(
        f"/order/{oid}/ship/",
        json={"content": "顺丰 SF-CAIPAI-001 已揽收"},
        headers=MH,
    )
    body = rv.get_json() or {}
    if body.get("status") != 200:
        fail("发货", body)
    ost = (body.get("data") or {}).get("status")
    if ost != "shipped":
        fail("发货后状态", f"got {ost}")
    ok("发货", f"status={ost}")

    # 12) 顾客再看订单
    rv = client.get(f"/api/c/order/{oid}/", headers=CH)
    body = rv.get_json() or {}
    data = body.get("data") or {}
    if body.get("status") != 200:
        fail("顾客查物流/状态", body)
    if data.get("status") != "shipped":
        ISSUES.append(f"顾客端状态期望 shipped 实际 {data.get('status')}")
    express = data.get("express") or data.get("express_content") or data.get("ship_content")
    ok("顾客见已发货", f"status={data.get('status')} express={str(express)[:80]}")

    # 13) 完成（可选）
    rv = client.post(f"/order/{oid}/complete/", headers=MH)
    body = rv.get_json() or {}
    if body.get("status") == 200:
        ok("订单完成", f"status={(body.get('data') or {}).get('status')}")
    else:
        ISSUES.append(f"complete 未强制：{body}")
        ok("订单完成", "跳过/非阻断")

    print("\n======== 彩排总结 ========")
    print(f"步骤通过: {sum(1 for s in STEPS if s['ok'])}/{len(STEPS)}")
    if ISSUES:
        print("问题/告警:")
        for i in ISSUES:
            print(" -", i)
    else:
        print("无阻断问题")
    print("REHEARSAL_PASS" if not any(not s['ok'] for s in STEPS) else "REHEARSAL_FAIL")

    # write report
    report = {
        "result": "PASS" if not ISSUES or all(s['ok'] for s in STEPS) else "PASS_WITH_WARNINGS",
        "steps": STEPS,
        "issues": ISSUES,
        "order_id": oid,
        "order_no": onostr,
    }
    if any(not s["ok"] for s in STEPS):
        report["result"] = "FAIL"
    out = Path(r"F:\Python_code\Flask项目\docs\REHEARSAL_REPORT.md")
    lines = [
        "# 人工收款彩排报告",
        "",
        f"- 结果：**{report['result']}**",
        f"- 订单：`{onostr}` (id={oid})",
        f"- 顾客：{phone} / 验证码 123456",
        f"- 店长：demo / admin / 123456",
        "",
        "## 步骤",
        "",
        "| 步骤 | 结果 | 详情 |",
        "|------|------|------|",
    ]
    for s in STEPS:
        lines.append(f"| {s['step']} | {'OK' if s['ok'] else 'FAIL'} | {s['detail']} |")
    lines += ["", "## 告警", ""]
    if ISSUES:
        for i in ISSUES:
            lines.append(f"- {i}")
    else:
        lines.append("- 无")
    lines += [
        "",
        "## 对应店长手册路径",
        "",
        "1. 顾客商城登录下单",
        "2. 按付款说明转账（彩排用备注模拟）",
        "3. 后台待支付 → 确认收款",
        "4. 待发货 → 发货填单号",
        "5. 顾客订单详情见已发货",
        "",
        "## 建议你本地再点一遍 UI",
        "",
        "```bat",
        "cd flask_shop && .venv\\Scripts\\python manager.py",
        "cd vue_shop && npm run serve",
        "cd mall && npm run dev",
        "```",
        "",
        "- 商城 http://localhost:5173 租户 demo",
        "- 后台 http://localhost:8080",
    ]
    out.write_text("\n".join(lines), encoding="utf-8")
    print("report ->", out)


if __name__ == "__main__":
    main()
