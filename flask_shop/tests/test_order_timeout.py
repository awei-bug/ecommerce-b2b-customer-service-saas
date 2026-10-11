# -*- coding: utf-8 -*-
from datetime import datetime, timedelta

from flask_shop import db, models
from flask_shop.utils.order_timeout import close_expired_pending_orders
from flask_shop.utils.tenant_query import tenant_context


def test_timeout_skips_claimed_pay(api, app):
    seed = api["seed"]
    with app.app_context(), tenant_context(disabled=True):
        old = datetime.now() - timedelta(hours=3)
        claimed = models.Order(
            tenant_id=seed["ta"].id,
            order_no="TO-CLAIM-1",
            price=10,
            status="pending_pay",
            buyer_paid_claimed=1,
            buyer_paid_note="ok",
        )
        plain = models.Order(
            tenant_id=seed["ta"].id,
            order_no="TO-PLAIN-1",
            price=10,
            status="pending_pay",
            buyer_paid_claimed=0,
        )
        db.session.add_all([claimed, plain])
        db.session.commit()
        claimed.create_time = old
        plain.create_time = old
        db.session.commit()
        n = close_expired_pending_orders(tenant_id=seed["ta"].id)
        claimed2 = models.Order.query.filter_by(order_no="TO-CLAIM-1").first()
        plain2 = models.Order.query.filter_by(order_no="TO-PLAIN-1").first()
        assert claimed2.status == "pending_pay"
        assert plain2.status == "closed"
        assert n >= 1


def test_dashboard_kpi_has_queues(api, app):
    seed = api["seed"]
    with app.app_context(), tenant_context(disabled=True):
        o = models.Order.query.get(seed["order_a"].id)
        o.buyer_paid_claimed = 1
        o.buyer_paid_note = "tail"
        db.session.commit()
    r = api["client"].get("/dashboard/kpi/", headers={"token": seed["token_a"]})
    body = r.get_json()
    assert body["status"] == 200
    data = body["data"]
    assert "queues" in data
    nos = [x["order_no"] for x in data["queues"]["claimed_pay"]]
    assert "A-ORD-1" in nos
    assert data["todo"]["claimed_pay"] >= 1


def test_dashboard_reports_owner_service_value_and_explicit_conversion(api, app):
    seed = api["seed"]
    now = datetime.now()
    with app.app_context(), tenant_context(disabled=True):
        customer = models.Customer(tenant_id=seed["id_a"], phone="13800009999", nickname="看板顾客")
        db.session.add(customer)
        db.session.flush()
        db.session.add_all([
            models.AgentTrace(
                tenant_id=seed["id_a"], session_id="dash-ai", channel="mall_chat",
                user_text="查商品", reply="商品回复", need_human=0, blocked=0,
            ),
            models.AgentTrace(
                tenant_id=seed["id_a"], session_id="dash-human", channel="mall_chat",
                user_text="退款", reply="转人工", need_human=1, blocked=0,
            ),
            models.SupportConversation(
                tenant_id=seed["id_a"], session_id="dash-human", customer_id=customer.id,
                status="resolved", need_human=0, satisfaction=5,
                first_response_at=now + timedelta(minutes=3), resolved_at=now + timedelta(minutes=8),
            ),
            models.Order(
                tenant_id=seed["id_a"], order_no="DASH-ASSISTED-1", customer_id=customer.id,
                price=88, status="paid", paid_at=now, consultation_session_id="dash-ai",
            ),
        ])
        db.session.commit()

    body = api["client"].get("/dashboard/kpi/", headers={"token": seed["token_a"]}).get_json()
    business = body["data"]["business"]
    assert business["service"]["sessions"] == 2
    assert business["service"]["ai_resolved"] == 1
    assert business["service"]["transferred"] == 1
    assert business["service"]["ai_resolution_rate"] == 50.0
    assert business["service"]["satisfaction"] == 5.0
    assert business["conversion"]["assisted_orders"] == 1
    assert business["conversion"]["assisted_paid_orders"] == 1
    assert business["conversion"]["assisted_gmv"] == 88.0
    assert business["conversion"]["method"] == "explicit_session_id"
