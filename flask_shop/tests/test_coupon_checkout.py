# -*- coding: utf-8 -*-
from flask_shop import db, models
from flask_shop.utils.token import generate_customer_token
from flask_shop.utils.tenant_query import tenant_context
from flask_shop.utils.money import money_float, money_mul


def _buyer(app, seed, phone="13900003333"):
    with app.app_context(), tenant_context(disabled=True):
        c = models.Customer(tenant_id=seed["ta"].id, phone=phone, nickname="c", status=1)
        db.session.add(c)
        db.session.commit()
        token = generate_customer_token(c)
        return c.id, token


def _enable_pay_qr(app, seed):
    with tenant_context(disabled=True):
        seed["ta"].pay_qr_wechat = "/static/upload/demo_qr.png"
        db.session.add(seed["ta"])
        db.session.commit()


def test_money_mul_avoids_binary_float():
    assert money_mul(0.1, 3) == 0.3
    assert money_float("10.005") == 10.01


def test_amount_off_coupon_applied(api, app):
    seed = api["seed"]
    _enable_pay_qr(app, seed)
    _cid, token = _buyer(app, seed)
    with app.app_context(), tenant_context(disabled=True):
        p = models.Product(tenant_id=seed["ta"].id, name="券商品199", price=199, number=10, state=2)
        cp = models.Coupon(
            tenant_id=seed["ta"].id, name="满199减20", coupon_type="amount_off",
            threshold=199, amount_off=20, status=1,
        )
        db.session.add_all([p, cp])
        db.session.commit()
        pid, cpid = p.id, cp.id
    r = api["client"].post(
        "/api/c/orders/",
        json={"items": [{"pid": pid, "number": 1}], "address": "测试地址", "coupon_id": cpid},
        headers={"token": token, "X-Tenant-Slug": "test-a"},
    )
    body = r.get_json()
    assert body["status"] == 200, body
    data = body["data"]
    assert float(data["goods_amount"]) == 199
    assert float(data["discount_amount"]) == 20
    assert float(data["price"]) == 179


def test_shipping_free_coupon(api, app):
    seed = api["seed"]
    _enable_pay_qr(app, seed)
    _cid, token = _buyer(app, seed, "13900004444")
    with app.app_context(), tenant_context(disabled=True):
        p = models.Product(tenant_id=seed["ta"].id, name="包邮商品", price=120, number=10, state=2)
        tpl = models.FreightTemplate(
            tenant_id=seed["ta"].id, name="固定8元", charge_type="fixed",
            fixed_fee=8, free_amount=0, is_default=1, status=1,
        )
        cp = models.Coupon(
            tenant_id=seed["ta"].id, name="满99包邮", coupon_type="shipping_free",
            threshold=99, amount_off=0, status=1,
        )
        db.session.add_all([p, tpl, cp])
        db.session.commit()
        pid, cpid = p.id, cp.id
    r = api["client"].post(
        "/api/c/orders/",
        json={"items": [{"pid": pid, "number": 1}], "address": "测试地址", "coupon_id": cpid},
        headers={"token": token, "X-Tenant-Slug": "test-a"},
    )
    body = r.get_json()
    assert body["status"] == 200, body
    data = body["data"]
    assert float(data["freight_amount"]) == 0
    assert float(data["discount_amount"]) == 8
    assert float(data["price"]) == 120


def test_freight_preview_applies_best_coupon(api, app):
    seed = api["seed"]
    with app.app_context(), tenant_context(disabled=True):
        db.session.add(models.Coupon(
            tenant_id=seed["ta"].id, name="预览满199减20", coupon_type="amount_off",
            threshold=199, amount_off=20, status=1,
        ))
        db.session.commit()
    r = api["client"].post(
        "/api/c/freight/preview/",
        json={"goods_amount": 199, "total_pieces": 1},
        headers={"X-Tenant-Slug": "test-a"},
    )
    body = r.get_json()
    assert body["status"] == 200, body
    data = body["data"]
    assert float(data["discount_amount"]) == 20
    assert float(data["pay_amount"]) == 179
    assert data["coupon"]["name"] == "预览满199减20"


def test_c_products_json_serializes_money(api):
    r = api["client"].get("/api/c/products/", headers={"X-Tenant-Slug": "test-a"})
    body = r.get_json()
    assert body["status"] == 200, body
    assert isinstance(body["data"], list)
    assert body["data"], body
    assert isinstance(body["data"][0]["price"], (int, float))


def test_c_order_rejected_without_pay_qr(api, app):
    seed = api["seed"]
    _cid, token = _buyer(app, seed, "13900005555")
    with app.app_context(), tenant_context(disabled=True):
        p = models.Product(tenant_id=seed["ta"].id, name="无码商品", price=88, number=5, state=2)
        db.session.add(p)
        db.session.commit()
        pid = p.id
    r = api["client"].post(
        "/api/c/orders/",
        json={"items": [{"pid": pid, "number": 1}], "address": "测试地址"},
        headers={"token": token, "X-Tenant-Slug": "test-a"},
    )
    body = r.get_json()
    assert body["status"] == 403, body
    assert "收款码" in (body.get("msg") or "")


def test_order_creation_persists_domestic_checkout(api, app):
    seed = api["seed"]
    _enable_pay_qr(app, seed)
    _cid, token = _buyer(app, seed, "13900006666")
    with app.app_context(), tenant_context(disabled=True):
        p = models.Product(tenant_id=seed["ta"].id, name="国内商品", price=50, number=5, state=2)
        db.session.add(p)
        db.session.commit()
        pid = p.id
    r = api["client"].post(
        "/api/c/orders/",
        json={"items": [{"pid": pid, "number": 1}], "address": "测试地址", "coupon_id": 0},
        headers={"token": token, "X-Tenant-Slug": "test-a"},
    )
    body = r.get_json()
    assert body["status"] == 200, body
    oid = body["data"]["id"]
    with app.app_context(), tenant_context(disabled=True):
        o = models.Order.query.get(oid)
        assert o is not None
        assert float(o.goods_amount) == 50
        assert o.status == "pending_pay"


def test_preview_skips_shipping_free_when_freight_already_zero(api, app):
    seed = api["seed"]
    with app.app_context(), tenant_context(disabled=True):
        db.session.add(models.FreightTemplate(
            tenant_id=seed["ta"].id, name="满99包邮模板", charge_type="fixed",
            fixed_fee=8, free_amount=99, is_default=1, status=1,
        ))
        db.session.add(models.Coupon(
            tenant_id=seed["ta"].id, name="满99包邮券", coupon_type="shipping_free",
            threshold=99, amount_off=0, status=1,
        ))
        db.session.add(models.Coupon(
            tenant_id=seed["ta"].id, name="满199减20", coupon_type="amount_off",
            threshold=199, amount_off=20, status=1,
        ))
        db.session.commit()
    r = api["client"].post(
        "/api/c/freight/preview/",
        json={"goods_amount": 120, "total_pieces": 1},
        headers={"X-Tenant-Slug": "test-a"},
    )
    body = r.get_json()
    assert body["status"] == 200, body
    data = body["data"]
    assert float(data["freight_amount"]) == 0
    assert float(data["discount_amount"]) == 0
    assert data.get("coupon") is None

