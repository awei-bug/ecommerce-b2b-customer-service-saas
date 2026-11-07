# -*- coding: utf-8 -*-
from datetime import datetime, timedelta

from flask_shop import db, models
from flask_shop.utils.order_timeout import close_expired_pending_orders
from flask_shop.utils.tenant_query import tenant_context
from flask_shop.utils.token import generate_token


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


def test_timeout_rechecks_order_after_candidate_is_claimed(api, app, monkeypatch):
    from flask_shop.utils import order_timeout

    tenant_id = api['seed']['id_a']
    with tenant_context(disabled=True):
        order = models.Order(tenant_id=tenant_id, order_no='TIMEOUT-CLAIM-RACE',
                             price=10, status='pending_pay', buyer_paid_claimed=0)
        db.session.add(order)
        db.session.commit()
        order.create_time = datetime.now() - timedelta(hours=3)
        db.session.commit()
        order_id = order.id

        def candidates_after_claim(deadline, candidate_tenant, limit):
            order.buyer_paid_claimed = 1
            db.session.commit()
            return [(order_id, tenant_id)]

        monkeypatch.setattr(order_timeout, '_timeout_candidates', candidates_after_claim)
        assert order_timeout.close_expired_pending_orders(tenant_id=tenant_id) == 0
        db.session.expire_all()
        saved = db.session.get(models.Order, order_id)
        assert saved.status == 'pending_pay'
        assert saved.buyer_paid_claimed == 1


def test_timeout_logs_failure_without_leaking_exception_text(api, app, monkeypatch, caplog):
    from flask_shop.utils import order_timeout

    tenant_id = api['seed']['id_a']
    with tenant_context(disabled=True):
        order = models.Order(tenant_id=tenant_id, order_no='TIMEOUT-FAIL', price=10,
                             status='pending_pay', buyer_paid_claimed=0)
        db.session.add(order)
        db.session.commit()
        order.create_time = datetime.now() - timedelta(hours=3)
        db.session.commit()
        order_id = order.id
        def fail_transit(*args, **kwargs):
            raise RuntimeError('sensitive exception detail')
        monkeypatch.setattr(order_timeout, 'transit_order', fail_transit)
        assert order_timeout.close_expired_pending_orders(tenant_id=tenant_id) == 0
        assert db.session.get(models.Order, order_id).status == 'pending_pay'
        assert 'auto-close failed' in caplog.text
        assert 'RuntimeError' in caplog.text
        assert 'sensitive exception detail' not in caplog.text


def test_timeout_counts_committed_order_when_audit_fails(api, app, monkeypatch, caplog):
    from flask_shop.utils import order_timeout

    tenant_id = api['seed']['id_a']
    with tenant_context(disabled=True):
        order = models.Order(tenant_id=tenant_id, order_no='TIMEOUT-AUDIT-FAIL', price=10,
                             status='pending_pay', buyer_paid_claimed=0)
        db.session.add(order)
        db.session.commit()
        order.create_time = datetime.now() - timedelta(hours=3)
        db.session.commit()
        order_id = order.id
        def fail_audit(*args, **kwargs):
            raise RuntimeError('audit failure detail')
        monkeypatch.setattr(order_timeout, 'write_audit', fail_audit)
        assert order_timeout.close_expired_pending_orders(tenant_id=tenant_id) == 1
        assert db.session.get(models.Order, order_id).status == 'closed'
        assert 'auto-close audit failed' in caplog.text
        assert 'audit failure detail' not in caplog.text


def test_timeout_logs_audit_helper_failure_result(api, app, monkeypatch, caplog):
    from flask_shop.utils import order_timeout

    tenant_id = api['seed']['id_a']
    with tenant_context(disabled=True):
        order = models.Order(tenant_id=tenant_id, order_no='TIMEOUT-AUDIT-RESULT', price=10,
                             status='pending_pay', buyer_paid_claimed=0)
        db.session.add(order)
        db.session.commit()
        order.create_time = datetime.now() - timedelta(hours=3)
        db.session.commit()
        monkeypatch.setattr(order_timeout, 'write_audit', lambda *args, **kwargs: False)
        assert order_timeout.close_expired_pending_orders(tenant_id=tenant_id) == 1
        assert 'auto-close audit failed' in caplog.text


def test_audit_failure_reports_type_without_sensitive_exception(api, app, monkeypatch, caplog):
    from flask_shop.utils.audit import write_audit

    def fail_insert(*args, **kwargs):
        raise RuntimeError('private-customer-data')

    monkeypatch.setattr('flask_shop.utils.audit.insert', fail_insert)
    assert write_audit('test.audit', tenant_id=api['seed']['id_a'], actor_type='system') is False
    assert 'audit write failed action=test.audit error_type=RuntimeError' in caplog.text
    assert 'private-customer-data' not in caplog.text


def test_audit_does_not_commit_or_rollback_caller_transaction(api, app, monkeypatch):
    from flask_shop.utils.audit import write_audit

    with tenant_context(disabled=True):
        product = db.session.get(models.Product, api['seed']['product_a'].id)
        original_name = product.name
        product.name = 'uncommitted-name'
        assert write_audit('test.independent', tenant_id=api['seed']['id_a'], actor_type='system') is True
        assert product.name == 'uncommitted-name'
        db.session.rollback()
        assert product.name == original_name
        assert models.AuditLog.query.filter_by(action='test.independent').count() == 1

        product.name = 'uncommitted-on-failure'
        def fail_insert(*args):
            raise RuntimeError('audit unavailable')

        monkeypatch.setattr('flask_shop.utils.audit.insert', fail_insert)
        assert write_audit('test.failure', tenant_id=api['seed']['id_a'], actor_type='system') is False
        assert product.name == 'uncommitted-on-failure'
        db.session.commit()
        assert product.name == 'uncommitted-on-failure'


def test_audit_rejects_shared_connection_with_active_caller_transaction(api, app, monkeypatch):
    from sqlalchemy.pool import StaticPool
    from flask_shop.utils.audit import write_audit

    product = db.session.get(models.Product, api['seed']['product_a'].id)
    product.name = 'pending-change'
    engine = db.engines['_audit']
    with monkeypatch.context() as patch:
        patch.setattr(engine, 'pool', StaticPool(creator=lambda: None))
        assert write_audit('test.shared', tenant_id=api['seed']['id_a'], actor_type='system') is False
    assert product.name == 'pending-change'
    db.session.rollback()


def test_audit_pool_is_separate_and_exhaustion_does_not_block_business(api, app):
    import time
    from flask_shop.utils.audit import write_audit

    audit_engine = db.engines['_audit']
    assert audit_engine.pool is not db.engine.pool
    product = db.session.get(models.Product, api['seed']['product_a'].id)
    product.name = 'pending-during-audit-pool-exhaustion'
    with audit_engine.connect(), audit_engine.connect():
        started = time.monotonic()
        assert write_audit('test.pool_exhausted', tenant_id=api['seed']['id_a'], actor_type='system') is False
        assert time.monotonic() - started < 3
    assert product.name == 'pending-during-audit-pool-exhaustion'
    db.session.commit()
    assert product.name == 'pending-during-audit-pool-exhaustion'


def test_in_memory_sqlite_audit_does_not_share_caller_connection(monkeypatch):
    from config import TestingConfig
    from flask_shop import create_app
    from flask_shop.utils.audit import write_audit

    monkeypatch.setattr(TestingConfig, 'SQLALCHEMY_DATABASE_URI', 'sqlite:///:memory:')
    isolated_app = create_app('test', initialize_schema=False, start_background=False)
    with isolated_app.app_context():
        db.create_all()
        product = models.Product(tenant_id=1, name='pending-memory-product', price=1)
        db.session.add(product)
        assert db.engines['_audit'].pool is not db.engine.pool
        assert write_audit('test.memory', tenant_id=1, actor_type='system') is False
        assert product in db.session.new
        db.session.rollback()


def test_audit_succeeds_when_business_pool_is_fully_checked_out(tmp_path, monkeypatch):
    from config import TestingConfig
    from flask_shop import create_app
    from flask_shop.utils.audit import write_audit

    monkeypatch.setattr(TestingConfig, 'SQLALCHEMY_DATABASE_URI', f'sqlite:///{(tmp_path / "audit.sqlite").as_posix()}')
    monkeypatch.setattr(TestingConfig, 'SQLALCHEMY_ENGINE_OPTIONS', {
        'pool_size': 1, 'max_overflow': 0, 'pool_timeout': 1,
    }, raising=False)
    isolated_app = create_app('test', initialize_schema=False, start_background=False)
    with isolated_app.app_context():
        db.create_all()
        db.session.execute(db.select(models.Product)).all()
        assert db.engine.pool.checkedout() == 1
        assert write_audit('test.separate_pool', tenant_id=1, actor_type='system') is True
        db.session.rollback()
        assert db.session.query(models.AuditLog).filter_by(action='test.separate_pool').count() == 1


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


def test_dashboard_open_support_queue_includes_older_conversations_only_for_current_tenant(api, app):
    seed = api["seed"]
    with app.app_context(), tenant_context(disabled=True):
        old = datetime.now() - timedelta(days=45)
        db.session.add_all([
            models.SupportConversation(tenant_id=seed["id_a"], session_id="old-waiting", status="waiting", create_time=old),
            models.SupportConversation(tenant_id=seed["id_a"], session_id="old-active", status="active", create_time=old),
            models.SupportConversation(tenant_id=seed["id_b"], session_id="other-waiting", status="waiting", create_time=old),
        ])
        db.session.commit()

    body = api["client"].get("/dashboard/kpi/", headers={"token": seed["token_a"]}).get_json()
    business = body["data"]["business"]
    assert business["service"]["waiting"] == 1
    assert business["service"]["active"] == 1
    assert next(item for item in business["priorities"] if item["code"] == "support_waiting")["count"] == 1


def test_dashboard_setup_uses_published_current_tenant_configuration(api, app):
    seed = api["seed"]
    with app.app_context(), tenant_context(disabled=True):
        seed["ta"].contact_phone = "  "
        seed["product_a"].state = 0
        db.session.add_all([
            models.StoreKnowledge(tenant_id=seed["id_a"], title="付款", content="付款说明", category="payment", status="published"),
            models.StoreKnowledge(tenant_id=seed["id_a"], title="发货草稿", content="配送说明", category="shipping", status="draft"),
            models.StoreKnowledge(tenant_id=seed["id_b"], title="其他店售后", content="售后说明", category="refund", status="published"),
        ])
        db.session.commit()

    setup = api["client"].get("/dashboard/kpi/", headers={"token": seed["token_a"]}).get_json()["data"]["setup"]
    assert setup["contact_configured"] is False
    assert setup["product_published"] is False
    assert setup["policy_categories"] == ["payment"]
    assert setup["can_edit_product"] and setup["can_edit_knowledge"] and setup["can_edit_staff"]


def test_dashboard_setup_requires_shop_settings_permission(api, app):
    seed = api["seed"]
    with app.app_context(), tenant_context(disabled=True):
        role = models.Role(tenant_id=seed["id_a"], name="报表查看", perm_codes='["report:read"]')
        db.session.add(role)
        db.session.flush()
        user = models.User(tenant_id=seed["id_a"], name="reporter", role_id=role.id)
        db.session.add(user)
        db.session.flush()
        token = generate_token({"typ": "merchant", "staff_id": user.id, "tenant_id": seed["id_a"]})
        db.session.commit()

    body = api["client"].get("/dashboard/kpi/", headers={"token": token}).get_json()
    assert body["status"] == 200
    assert body["data"]["setup"] is None


def test_dashboard_setup_indicates_missing_edit_permissions(api, app):
    seed = api["seed"]
    with app.app_context(), tenant_context(disabled=True):
        role = models.Role(tenant_id=seed["id_a"], name="店铺查看", perm_codes='["report:read", "shop:settings"]')
        db.session.add(role)
        db.session.flush()
        user = models.User(tenant_id=seed["id_a"], name="shop_viewer", role_id=role.id)
        db.session.add(user)
        db.session.flush()
        token = generate_token({"typ": "merchant", "staff_id": user.id, "tenant_id": seed["id_a"]})
        db.session.commit()

    setup = api["client"].get("/dashboard/kpi/", headers={"token": token}).get_json()["data"]["setup"]
    assert setup["can_edit_product"] is False
    assert setup["can_edit_knowledge"] is False
    assert setup["can_edit_staff"] is False
