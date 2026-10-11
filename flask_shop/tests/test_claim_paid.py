# -*- coding: utf-8 -*-
from flask_shop import db, models
from flask_shop.utils.token import generate_customer_token
from flask_shop.utils.tenant_query import tenant_context


def _customer_order(app, seed):
    with app.app_context(), tenant_context(disabled=True):
        c = models.Customer(
            tenant_id=seed["ta"].id,
            phone="13900001111",
            nickname="buyer",
            status=1,
        )
        db.session.add(c)
        db.session.commit()
        order = models.Order.query.get(seed["order_a"].id)
        order.customer_id = c.id
        db.session.commit()
        token = generate_customer_token(c)
        return c.id, order.id, token


def test_customer_can_claim_paid(api, app):
    cid, oid, token = _customer_order(app, api["seed"])
    headers = {"token": token, "X-Tenant-Slug": "test-a"}
    r = api["client"].post(
        f"/api/c/order/{oid}/claim-paid/",
        json={"note": "wei1234"},
        headers=headers,
    )
    body = r.get_json()
    assert r.status_code == 200
    assert body["status"] == 200
    assert body["data"]["buyer_paid_claimed"] == 1
    assert body["data"]["buyer_paid_note"] == "wei1234"
    assert body["data"]["status"] == "pending_pay"


def test_cannot_claim_other_customer_order(api, app):
    _cid, oid, token = _customer_order(app, api["seed"])
    with app.app_context(), tenant_context(disabled=True):
        other = models.Customer(
            tenant_id=api["seed"]["ta"].id,
            phone="13900002222",
            nickname="other",
            status=1,
        )
        db.session.add(other)
        db.session.commit()
        other_token = generate_customer_token(other)
    headers = {"token": other_token, "X-Tenant-Slug": "test-a"}
    r = api["client"].post(
        f"/api/c/order/{oid}/claim-paid/",
        json={"note": "x"},
        headers=headers,
    )
    assert r.get_json()["status"] == 404


def test_admin_can_filter_claimed(api, app):
    _cid, oid, token = _customer_order(app, api["seed"])
    headers = {"token": token, "X-Tenant-Slug": "test-a"}
    api["client"].post(
        f"/api/c/order/{oid}/claim-paid/",
        json={"note": "ok"},
        headers=headers,
    )
    staff = {"token": api["seed"]["token_a"]}
    r = api["client"].get("/orders/?status=pending_pay&claimed=1", headers=staff)
    body = r.get_json()
    assert body["status"] == 200
    nos = [o["order_no"] for o in body["data"]]
    assert "A-ORD-1" in nos
    assert all(int(o.get("buyer_paid_claimed") or 0) == 1 for o in body["data"])