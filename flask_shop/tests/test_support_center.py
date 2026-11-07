from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event

import pytest

from flask_shop import db, models
from flask_shop.utils.token import generate_token
from flask_shop.utils.tenant_query import tenant_context


@pytest.fixture(autouse=True)
def reset_rate_limit_buckets():
    from flask_shop.utils.rate_limit import _buckets, _lock

    with _lock:
        _buckets.clear()
    yield
    with _lock:
        _buckets.clear()


def _chat_result(*, need_human=True):
    return {
        "status": 200,
        "msg": "ok",
        "data": {
            "reply": "我已为你转接人工客服。",
            "intent": {"intent": "cs", "label": "人工客服"},
            "products": [],
            "actions": [],
            "need_human": need_human,
            "blocked": False,
            "agents_ran": ["intent", "cs"],
            "suggested_replies": [],
        },
    }


def _prepare_customer(app, tenant, phone="13800000001"):
    with app.app_context(), tenant_context(disabled=True):
        customer = models.Customer(tenant_id=tenant.id, phone=phone, nickname="测试顾客")
        db.session.add(customer)
        db.session.commit()
        return customer.id, generate_token({
            "typ": "customer",
            "customer_id": customer.id,
            "tenant_id": tenant.id,
        })


def test_followup_message_alias_preserves_original_customer_text(api, app):
    followup = {'is_followup': True, 'product': {'id': 123, 'name': '示例商品', 'price': 9}, 'index': 0}
    with patch('flask_shop.agents.views.resolve_followup', return_value=followup), \
         patch('flask_shop.agents.views.orchestrator.run_chat', return_value=_chat_result(need_human=False)) as run_chat:
        response = api['client'].post('/api/agents/chat/', headers={'X-Tenant-Slug': 'test-a'},
                                      json={'message': ' 买第1个 ', 'session_id': 'alias-followup'}).get_json()
    assert response['status'] == 200
    assert '示例商品' in run_chat.call_args.args[0]
    with app.app_context(), tenant_context(disabled=True):
        conversation = models.SupportConversation.query.filter_by(session_id='alias-followup').one()
        assert conversation.messages.filter_by(sender_type='customer').one().content == '买第1个'
        assert models.AgentTrace.query.filter_by(session_id='alias-followup').one().user_text == '买第1个'


def test_followup_refreshes_memory_price_stock_and_filters_cross_tenant(api, app):
    seed = api['seed']
    with app.app_context(), tenant_context(disabled=True):
        product = db.session.get(models.Product, seed['product_a'].id)
        product.name = '当前商品'
        product.price = 55
        product.number = 8
        db.session.add(models.ProductSku(tenant_id=seed['id_a'], product_id=product.id, stock=2, status=1))
        db.session.commit()
    old = [{'id': seed['product_a'].id, 'name': '旧商品', 'price': 1, 'stock': 50},
           {'id': seed['product_b'].id, 'name': '其他店商品', 'price': 2}]
    memory = {'last_products': old, 'summary': '旧价格 1 元',
              'recent_turns': [{'role': 'assistant', 'text': '旧价格 1 元'}, {'role': 'user', 'text': '想买商品'}],
              'preferences': {'last_product_names': ['旧商品'], 'budget_max': 100}}
    with patch('flask_shop.agents.views.get_session', return_value={'last_products': old}), \
         patch('flask_shop.agents.support.get_memory_context', return_value=memory), \
         patch('flask_shop.agents.views.orchestrator.run_chat', return_value=_chat_result(need_human=False)) as run_chat:
        response = api['client'].post('/api/agents/chat/', headers={'X-Tenant-Slug': 'test-a'},
                                      json={'text': '买第1个', 'session_id': 'fresh-followup'}).get_json()
    assert response['status'] == 200
    assert response['data']['followup']['product'] == {
        'id': seed['product_a'].id, 'name': '当前商品', 'price': 55.0, 'stock': 2, 'in_stock': True,
    }
    assert '价格55.0, 库存2' in run_chat.call_args.args[0]
    safe_memory = run_chat.call_args.kwargs['memory']
    assert len(safe_memory['last_products']) == 1
    assert safe_memory['summary'] == ''
    assert safe_memory['recent_turns'] == [{'role': 'user', 'text': '想买商品'}]
    assert safe_memory['preferences'] == {'budget_max': 100}


def test_followup_does_not_shift_or_reuse_unavailable_product(api, app):
    seed = api['seed']
    with app.app_context(), tenant_context(disabled=True):
        db.session.get(models.Product, seed['product_a'].id).state = 0
        available = models.Product(tenant_id=seed['id_a'], name='第二件在售商品', price=30, number=2)
        db.session.add(available)
        db.session.commit()
        available_id = available.id
    old = [{'id': seed['product_a'].id, 'name': '下架商品', 'price': 1},
           {'id': available_id, 'name': '第二件旧商品', 'price': 2}]
    with patch('flask_shop.agents.views.get_session', return_value={'last_products': old}), \
         patch('flask_shop.agents.views.orchestrator.run_chat', return_value=_chat_result(need_human=False)) as run_chat:
        response = api['client'].post('/api/agents/chat/', headers={'X-Tenant-Slug': 'test-a'},
                                      json={'text': '买第1个', 'session_id': 'unavailable-followup'}).get_json()
    assert response['status'] == 200
    assert response['data']['followup']['product'] is None
    assert '已下架或暂时无法确认' in response['data']['reply']
    run_chat.assert_not_called()


def test_followup_discards_cached_details_if_refresh_fails(api):
    old = [{'id': 1, 'name': '旧商品', 'price': 1}]
    with patch('flask_shop.agents.views.get_session', return_value={'last_products': old}), \
         patch('flask_shop.agents.support.get_memory_context', return_value={'last_products': old}), \
         patch('flask_shop.agents.support.refresh_product_slots', side_effect=RuntimeError('unavailable')), \
         patch('flask_shop.agents.views.orchestrator.run_chat', return_value=_chat_result(need_human=False)) as run_chat:
        response = api['client'].post('/api/agents/chat/', headers={'X-Tenant-Slug': 'test-a'},
                                      json={'text': '买第1个', 'session_id': 'refresh-failure'}).get_json()
    assert response['status'] == 200
    assert '暂时无法确认' in response['data']['reply']
    run_chat.assert_not_called()
    assert 'followup' not in response['data']


def test_sold_out_followup_gives_deterministic_reply_and_persists_history(api, app):
    seed = api['seed']
    with app.app_context(), tenant_context(disabled=True):
        product_id = seed['product_a'].id
        db.session.add(models.ProductSku(tenant_id=seed['id_a'], product_id=product_id, stock=0, status=1))
        db.session.commit()
    old = [{'id': product_id, 'name': '旧商品', 'price': 1, 'stock': 50}]
    with patch('flask_shop.agents.views.get_session', return_value={'last_products': old}), \
         patch('flask_shop.agents.views.orchestrator.run_chat') as run_chat:
        response = api['client'].post('/api/agents/chat/', headers={'X-Tenant-Slug': 'test-a'},
                                      json={'text': '买第1个', 'session_id': 'sold-out-followup'}).get_json()
    assert response['status'] == 200
    assert '缺货' in response['data']['reply']
    assert response['data']['followup']['product']['in_stock'] is False
    run_chat.assert_not_called()
    with app.app_context(), tenant_context(disabled=True):
        conversation = models.SupportConversation.query.filter_by(session_id='sold-out-followup').one()
        assert [(item.sender_type, item.content) for item in conversation.messages.all()] == [
            ('customer', '买第1个'), ('ai', response['data']['reply']),
        ]


@pytest.mark.parametrize('payload', [[], {'text': 123}, {'text': 'x' * 8001}])
def test_chat_rejects_invalid_or_oversized_messages_before_ai(api, payload):
    with patch('flask_shop.agents.views.orchestrator.run_chat') as run_chat:
        response = api['client'].post('/api/agents/chat/', headers={'X-Tenant-Slug': 'test-a'}, json=payload)
    assert response.status_code == 400
    run_chat.assert_not_called()


def test_staff_reply_rejects_oversized_message_without_claiming_conversation(api, app):
    with app.app_context(), tenant_context(disabled=True):
        conversation = models.SupportConversation(tenant_id=api['seed']['id_a'], session_id='long-reply', status='waiting')
        db.session.add(conversation)
        db.session.commit()
        conversation_id = conversation.id
    response = api['client'].post(f'/api/agents/support/conversations/{conversation_id}/reply/',
                                  headers={'token': api['seed']['token_a']}, json={'content': 'x' * 8001})
    assert response.status_code == 400
    with app.app_context(), tenant_context(disabled=True):
        conversation = db.session.get(models.SupportConversation, conversation_id)
        assert conversation.status == 'waiting' and conversation.assignee_id is None
        assert conversation.messages.count() == 0


def test_support_handoff_claim_reply_resolve_and_rate(api, app):
    client = api["client"]
    seed = api["seed"]
    customer_id, customer_token = _prepare_customer(app, seed["ta"])
    mall_headers = {"X-Tenant-Slug": "test-a", "token": customer_token}
    staff_headers = {"token": seed["token_a"]}

    with patch("flask_shop.agents.views.orchestrator.run_chat", return_value=_chat_result()) as run_chat:
        response = client.post(
            "/api/agents/chat/",
            json={"text": "转店长", "session_id": "support-e2e"},
            headers=mall_headers,
        ).get_json()

    assert response["status"] == 200
    assert response["data"]["support"]["status"] == "waiting"
    assert response["data"]["support"]["customer_id"] == customer_id
    assert response["data"]["customer_message_id"] < response["data"]["ai_message_id"]
    run_chat.assert_called_once()

    inbox = client.get(
        "/api/agents/support/inbox/?status=waiting",
        headers=staff_headers,
    ).get_json()
    assert inbox["status"] == 200
    assert inbox["data"]["counts"]["waiting"] == 1
    conversation = inbox["data"]["items"][0]
    conversation_id = conversation["id"]

    detail = client.get(
        f"/api/agents/support/conversations/{conversation_id}/",
        headers=staff_headers,
    ).get_json()
    assert [item["sender_type"] for item in detail["data"]["messages"]] == ["customer", "ai"]

    claimed = client.post(
        f"/api/agents/support/conversations/{conversation_id}/claim/",
        headers=staff_headers,
    ).get_json()
    assert claimed["status"] == 200
    assert claimed["data"]["status"] == "active"

    with patch("flask_shop.agents.views.orchestrator.run_chat") as run_chat_again:
        queued = client.post(
            "/api/agents/chat/",
            json={"text": "请问什么时候能处理", "session_id": "support-e2e"},
            headers=mall_headers,
        ).get_json()
    assert queued["status"] == 200
    assert queued["data"]["agents_ran"] == ["support_queue"]
    assert queued["data"]["customer_message_id"] > response["data"]["ai_message_id"]
    run_chat_again.assert_not_called()

    replied = client.post(
        f"/api/agents/support/conversations/{conversation_id}/reply/",
        json={"content": "您好，我来帮您处理。"},
        headers=staff_headers,
    ).get_json()
    assert replied["status"] == 200

    customer_messages = client.get(
        "/api/agents/support/session/support-e2e/messages/?after_id=2",
        headers=mall_headers,
    ).get_json()
    sender_types = [item["sender_type"] for item in customer_messages["data"]["messages"]]
    assert "staff" in sender_types
    assert "system" in sender_types

    resolved = client.post(
        f"/api/agents/support/conversations/{conversation_id}/resolve/",
        headers=staff_headers,
    ).get_json()
    assert resolved["status"] == 200
    assert resolved["data"]["status"] == "resolved"

    rated = client.post(
        "/api/agents/support/session/support-e2e/satisfaction/",
        json={"score": 5, "note": "处理很快"},
        headers=mall_headers,
    ).get_json()
    assert rated["status"] == 200
    assert rated["data"]["satisfaction"] == 5


def test_customer_history_paginates_without_losing_messages(api, app):
    client = api["client"]
    headers = {"X-Tenant-Slug": "test-a"}
    with patch("flask_shop.agents.views.orchestrator.run_chat", return_value=_chat_result(need_human=False)):
        chat = client.post(
            "/api/agents/chat/",
            json={"text": "你好", "session_id": "history-pages"},
            headers=headers,
        ).get_json()
    assert chat["status"] == 200
    with app.app_context(), tenant_context(disabled=True):
        conversation = models.SupportConversation.query.filter_by(session_id="history-pages").one()
        db.session.add_all([
            models.SupportMessage(tenant_id=conversation.tenant_id, conversation_id=conversation.id,
                                  sender_type="system", content=f"消息 {index}")
            for index in range(100)
        ])
        db.session.commit()

    first = client.get("/api/agents/support/session/history-pages/messages/", headers=headers).get_json()["data"]
    second = client.get(
        f"/api/agents/support/session/history-pages/messages/?after_id={first['messages'][-1]['id']}",
        headers=headers,
    ).get_json()["data"]
    assert len(first["messages"]) == 100
    assert first["has_more"] is True
    assert len(second["messages"]) == 2
    assert second["has_more"] is False
    ids = [message["id"] for message in first["messages"] + second["messages"]]
    assert ids == sorted(set(ids))


def test_history_rehydrates_current_tenant_products_and_safe_actions(api, app):
    client = api["client"]
    seed = api["seed"]
    product_id = seed["product_a"].id
    other_product_id = seed["product_b"].id
    headers = {"X-Tenant-Slug": "test-a"}
    result = _chat_result(need_human=False)
    result["data"].update({
        "products": [{"id": product_id, "name": "旧名称", "price": 1}, {"id": other_product_id}],
        "draft_order_hint": {"product_id": product_id, "path": "https://invalid.example"},
        "actions": [
            {"type": "login", "path": "/login?redirect=/orders"},
            {"type": "human", "path": "tel:111111"},
            {"type": "orders", "path": "https://invalid.example"},
        ],
        "login_required": True,
    })
    with patch("flask_shop.agents.views.orchestrator.run_chat", return_value=result):
        chat = client.post("/api/agents/chat/", json={"text": "推荐商品", "session_id": "replay-products"}, headers=headers)
    assert chat.get_json()["status"] == 200

    with app.app_context(), tenant_context(disabled=True):
        product = db.session.get(models.Product, product_id)
        product.name = "当前商品"
        product.price = 25
        product.number = 9
        db.session.add(models.ProductSku(tenant_id=seed["id_a"], product_id=product_id, stock=2, status=1))
        db.session.get(models.Tenant, seed["id_a"]).contact_phone = "13800138000"
        db.session.commit()

    history_url = "/api/agents/support/session/replay-products/messages/"
    history = client.get(history_url, headers=headers).get_json()["data"]["messages"]
    extra = history[-1]["extra"]
    assert "product_ids" not in extra
    assert extra["products"] == [{"id": product_id, "name": "当前商品", "price": 25.0, "stock": 2, "in_stock": True}]
    assert extra["draft_order_hint"] == {"name": "当前商品", "path": f"/product/{product_id}?buy=1"}
    assert extra["actions"] == [
        {"type": "login", "label": "去登录查订单", "path": "/login?redirect=/orders"},
        {"type": "human", "label": "联系店长 13800138000", "path": "tel:13800138000"},
    ]

    customer_id, token = _prepare_customer(app, seed["ta"], phone="13800000009")
    signed_in = client.get(history_url, headers={**headers, "token": token}).get_json()["data"]["messages"][-1]["extra"]
    assert signed_in["login_required"] is False
    assert all(action["type"] != "login" for action in signed_in["actions"])
    assert customer_id

    with app.app_context(), tenant_context(disabled=True):
        sku = models.ProductSku.query.filter_by(product_id=product_id).one()
        sku.stock = 0
        db.session.commit()
    sold_out = client.get(history_url, headers=headers).get_json()["data"]["messages"][-1]["extra"]
    assert sold_out["products"][0]["in_stock"] is False
    assert sold_out["draft_order_hint"] is None

    with app.app_context(), tenant_context(disabled=True):
        db.session.get(models.Product, product_id).state = 0
        db.session.commit()
    unavailable = client.get(history_url, headers=headers).get_json()["data"]["messages"][-1]["extra"]
    assert unavailable["products"] == []
    assert unavailable["draft_order_hint"] is None


def test_support_conversation_is_tenant_scoped_and_cannot_be_stolen(api, app):
    client = api["client"]
    seed = api["seed"]
    with app.app_context(), tenant_context(disabled=True):
        row = models.SupportConversation(
            tenant_id=seed["id_a"],
            session_id="tenant-a-only",
            status="waiting",
            need_human=1,
            subject="A 租户会话",
        )
        role = models.Role.query.filter_by(tenant_id=seed["id_a"], name="超级管理员").first()
        db.session.add(row)
        db.session.flush()
        other_staff = models.User(tenant_id=seed["id_a"], name="support_other", role_id=role.id)
        other_staff.password = "123456"
        db.session.add(other_staff)
        db.session.commit()
        conversation_id = row.id
        other_token = generate_token({
            "typ": "merchant",
            "staff_id": other_staff.id,
            "tenant_id": seed["id_a"],
        })

    claimed = client.post(
        f"/api/agents/support/conversations/{conversation_id}/claim/",
        headers={"token": seed["token_a"]},
    ).get_json()
    assert claimed["status"] == 200

    stolen = client.post(
        f"/api/agents/support/conversations/{conversation_id}/claim/",
        headers={"token": other_token},
    ).get_json()
    assert stolen["status"] == 409

    other_tenant_detail = client.get(
        f"/api/agents/support/conversations/{conversation_id}/",
        headers={"token": seed["token_b"]},
    ).get_json()
    assert other_tenant_detail["status"] == 404

    other_tenant_inbox = client.get(
        "/api/agents/support/inbox/?status=all",
        headers={"token": seed["token_b"]},
    ).get_json()
    assert other_tenant_inbox["status"] == 200
    assert other_tenant_inbox["data"]["items"] == []


def test_support_order_summary_requires_order_permission_and_stays_tenant_scoped(api, app):
    seed = api["seed"]
    with app.app_context(), tenant_context(disabled=True):
        customer = models.Customer(tenant_id=seed["id_a"], phone="13800001234")
        db.session.add(customer)
        db.session.flush()
        conversation = models.SupportConversation(
            tenant_id=seed["id_a"], customer_id=customer.id, session_id="order-summary", status="waiting",
        )
        db.session.add_all([
            conversation,
            models.Order(tenant_id=seed["id_a"], customer_id=customer.id, order_no="VISIBLE-ORDER", price=29,
                         status="refunding", address="private address"),
            models.Order(tenant_id=seed["id_b"], customer_id=customer.id, order_no="OTHER-TENANT", price=50),
        ])
        role = models.Role(tenant_id=seed["id_a"], name="仅客服", perm_codes='["service:read"]')
        db.session.add(role)
        db.session.flush()
        staff = models.User(tenant_id=seed["id_a"], name="service_only", role_id=role.id)
        db.session.add(staff)
        db.session.flush()
        restricted_token = generate_token({"typ": "merchant", "staff_id": staff.id, "tenant_id": seed["id_a"]})
        conversation_id = conversation.id
        db.session.commit()

    path = f"/api/agents/support/conversations/{conversation_id}/"
    restricted = api["client"].get(path, headers={"token": restricted_token}).get_json()["data"]
    assert restricted["orders_allowed"] is False
    assert restricted["orders"] == []

    permitted = api["client"].get(path, headers={"token": seed["token_a"]}).get_json()["data"]
    assert permitted["orders_allowed"] is True
    assert permitted["orders"] == [{"id": permitted["orders"][0]["id"], "order_no": "VISIBLE-ORDER", "status": "refunding", "price": 29.0}]
    assert api["client"].get(path, headers={"token": seed["token_b"]}).get_json()["status"] == 404


def test_chat_rejects_other_customer_and_anonymous_access_to_bound_session(api, app):
    seed = api["seed"]
    customer_id, owner_token = _prepare_customer(app, seed["ta"], "13800000011")
    _, other_token = _prepare_customer(app, seed["ta"], "13800000012")
    with app.app_context(), tenant_context(disabled=True):
        for status in ("bot", "waiting", "active", "resolved"):
            db.session.add(models.SupportConversation(
                tenant_id=seed["id_a"], customer_id=customer_id, session_id=f"owned-{status}", status=status,
            ))
        db.session.commit()

    with patch("flask_shop.agents.views.orchestrator.run_chat", return_value=_chat_result(need_human=False)) as run_chat:
        for status in ("bot", "waiting", "active", "resolved"):
            for token in (None, other_token):
                headers = {"X-Tenant-Slug": "test-a"}
                if token:
                    headers["token"] = token
                result = api["client"].post("/api/agents/chat/", headers=headers,
                                            json={"text": "冒充顾客", "session_id": f"owned-{status}"})
                assert result.status_code == 403
            run_chat.assert_not_called()
        owned = api["client"].post("/api/agents/chat/", headers={"X-Tenant-Slug": "test-a", "token": owner_token},
                                   json={"text": "本人消息", "session_id": "owned-waiting"})
        assert owned.get_json()["data"]["agents_ran"] == ["support_queue"]
        run_chat.assert_not_called()


def test_chat_rejects_foreign_tenant_token_and_fails_closed_on_support_error(api, app):
    seed = api["seed"]
    _, foreign_token = _prepare_customer(app, seed["tb"], "13800000013")
    with patch("flask_shop.agents.views.orchestrator.run_chat") as run_chat:
        result = api["client"].post("/api/agents/chat/", headers={"X-Tenant-Slug": "test-a", "token": foreign_token},
                                    json={"text": "你好"})
        assert result.status_code == 403
        with patch("flask_shop.agents.support.get_conversation", side_effect=RuntimeError("database unavailable")):
            result = api["client"].post("/api/agents/chat/", headers={"X-Tenant-Slug": "test-a"},
                                        json={"text": "你好"})
        assert result.status_code == 503
        run_chat.assert_not_called()


def test_chat_followup_cache_isolated_by_tenant(api, app):
    from flask_shop.agents.memory import save_session

    seed = api["seed"]
    save_session(f'{seed["id_a"]}:same-session', user_text="商品", reply="推荐",
                 products=[{"id": 123, "name": "A租户专属商品", "price": 9}])
    with patch("flask_shop.agents.views.orchestrator.run_chat", return_value=_chat_result(need_human=False)) as run_chat:
        result = api["client"].post("/api/agents/chat/", headers={"X-Tenant-Slug": "test-b"},
                                    json={"text": "买第1个", "session_id": "same-session"})
    assert result.get_json()["status"] == 200
    assert run_chat.call_args.args[0] == "买第1个"


def test_disabled_customer_cannot_access_chat_or_history(api, app):
    seed = api["seed"]
    customer_id, token = _prepare_customer(app, seed["ta"], "13800000014")
    with app.app_context(), tenant_context(disabled=True):
        db.session.add(models.SupportConversation(tenant_id=seed["id_a"], customer_id=customer_id,
                                                  session_id="disabled-customer", status="waiting"))
        db.session.get(models.Customer, customer_id).status = 0
        db.session.commit()

    headers = {"X-Tenant-Slug": "test-a", "token": token}
    history = api["client"].get("/api/agents/support/session/disabled-customer/messages/", headers=headers)
    chat = api["client"].post("/api/agents/chat/", headers=headers,
                              json={"text": "你好", "session_id": "disabled-customer"})
    assert history.status_code == 401
    assert chat.status_code == 401


def test_concurrent_staff_actions_have_single_owner(api, app):
    from flask_shop.agents import views

    seed = api["seed"]
    with app.app_context(), tenant_context(disabled=True):
        role = models.Role.query.filter_by(tenant_id=seed["id_a"], name="超级管理员").first()
        second_staff = models.User(tenant_id=seed["id_a"], name="concurrent_staff", role_id=role.id)
        conversation = models.SupportConversation(tenant_id=seed["id_a"], session_id="concurrent-claim", status="waiting")
        db.session.add_all([second_staff, conversation])
        db.session.flush()
        second_token = generate_token({"typ": "merchant", "staff_id": second_staff.id, "tenant_id": seed["id_a"]})
        conversation_id = conversation.id
        db.session.commit()

    barrier = Barrier(2)
    original = views._support_row

    def synchronized_row(row_id):
        row = original(row_id)
        barrier.wait(timeout=10)
        return row

    def perform(token, action):
        with app.test_client() as client:
            response = client.post(f"/api/agents/support/conversations/{conversation_id}/{action}/",
                                   headers={"token": token}, json={"content": "客服回复"})
            return response.get_json()

    with patch.object(views, "_support_row", side_effect=synchronized_row):
        with ThreadPoolExecutor(max_workers=2) as pool:
            claim = pool.submit(perform, seed["token_a"], "claim")
            reply = pool.submit(perform, second_token, "reply")
            outcomes = [claim.result(timeout=20), reply.result(timeout=20)]
    assert sorted(item["status"] for item in outcomes) == [200, 409]

    with app.app_context(), tenant_context(disabled=True):
        row = db.session.get(models.SupportConversation, conversation_id)
        messages = row.messages.all()
        assert row.status == "active"
        assert len(messages) == 1
        assert messages[0].sender_id == row.assignee_id
        assert row.message_count == 1


def test_claim_is_idempotent_and_closed_conversation_cannot_be_resolved_twice(api, app):
    seed = api["seed"]
    with app.app_context(), tenant_context(disabled=True):
        row = models.SupportConversation(tenant_id=seed["id_a"], session_id="claim-repeat", status="waiting")
        db.session.add(row)
        db.session.commit()
        conversation_id = row.id
    path = f"/api/agents/support/conversations/{conversation_id}/"
    headers = {"token": seed["token_a"]}
    assert api["client"].post(path + "claim/", headers=headers).get_json()["status"] == 200
    assert api["client"].post(path + "claim/", headers=headers).get_json()["status"] == 200
    assert api["client"].post(path + "resolve/", headers=headers).get_json()["status"] == 200
    assert api["client"].post(path + "resolve/", headers=headers).get_json()["status"] == 409
    with app.app_context(), tenant_context(disabled=True):
        row = db.session.get(models.SupportConversation, conversation_id)
        assert row.message_count == 2
        assert row.messages.count() == 2


@pytest.mark.parametrize("finish_service", [False, True])
def test_ai_response_is_discarded_if_human_takes_over_during_generation(api, app, finish_service):
    seed = api["seed"]
    with app.app_context(), tenant_context(disabled=True):
        conversation = models.SupportConversation(tenant_id=seed["id_a"], session_id="slow-ai", status="bot")
        db.session.add(conversation)
        db.session.commit()
        conversation_id = conversation.id

    model_started = Event()
    allow_model_to_finish = Event()

    def slow_model(*args, **kwargs):
        model_started.set()
        assert allow_model_to_finish.wait(timeout=15)
        return _chat_result(need_human=True)

    def send_message():
        with app.test_client() as client:
            return client.post("/api/agents/chat/", headers={"X-Tenant-Slug": "test-a"},
                               json={"text": "顾客问题", "session_id": "slow-ai"}).get_json()

    with patch("flask_shop.agents.views.orchestrator.run_chat", side_effect=slow_model):
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(send_message)
            assert model_started.wait(timeout=10)
            path = f"/api/agents/support/conversations/{conversation_id}/"
            headers = {"token": seed["token_a"]}
            try:
                assert api["client"].post(path + "claim/", headers=headers).get_json()["status"] == 200
                if finish_service:
                    assert api["client"].post(path + "resolve/", headers=headers).get_json()["status"] == 200
            finally:
                allow_model_to_finish.set()
            result = future.result(timeout=15)

    expected_status = "resolved" if finish_service else "active"
    assert result["status"] == 200
    assert result["data"]["agents_ran"] == ["support_queue"]
    assert result["data"]["support"]["status"] == expected_status
    assert result["data"]["reply"] != _chat_result()["data"]["reply"]
    with app.app_context(), tenant_context(disabled=True):
        row = db.session.get(models.SupportConversation, conversation_id)
        messages = row.messages.all()
        assert row.status == expected_status
        assert [message.sender_type for message in messages].count("customer") == 1
        assert all(message.sender_type != "ai" for message in messages)
        assert row.message_count == len(messages)
        assert models.AgentMemory.query.filter_by(tenant_id=seed["id_a"], scope_key="session:slow-ai").first() is None


def test_simultaneous_new_session_handoff_preserves_both_customer_messages(api, app):
    seed = api["seed"]
    model_barrier = Barrier(2)

    def simultaneous_model(*args, **kwargs):
        model_barrier.wait(timeout=10)
        return _chat_result(need_human=True)

    def send_message(text):
        with app.test_client() as client:
            response = client.post("/api/agents/chat/", headers={"X-Tenant-Slug": "test-a"},
                                   json={"text": text, "session_id": "simultaneous-new"})
            return response.get_json()

    with patch("flask_shop.agents.views.orchestrator.run_chat", side_effect=simultaneous_model):
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(send_message, "第一条消息")
            second = pool.submit(send_message, "第二条消息")
            outcomes = [first.result(timeout=20), second.result(timeout=20)]
    assert all(outcome["status"] == 200 for outcome in outcomes)
    assert sorted(outcome["data"]["agents_ran"] == ["support_queue"] for outcome in outcomes) == [False, True]

    with app.app_context(), tenant_context(disabled=True):
        row = models.SupportConversation.query.filter_by(tenant_id=seed["id_a"], session_id="simultaneous-new").one()
        messages = row.messages.all()
        assert row.status == "waiting"
        assert {message.content for message in messages if message.sender_type == "customer"} == {"第一条消息", "第二条消息"}
        assert [message.sender_type for message in messages].count("ai") == 1
        assert row.message_count == len(messages) == 3


def test_ai_response_is_rejected_if_session_gets_bound_to_another_customer(api, app):
    seed = api["seed"]
    customer_id, _ = _prepare_customer(app, seed["ta"], "13800000015")
    with app.app_context(), tenant_context(disabled=True):
        row = models.SupportConversation(tenant_id=seed["id_a"], session_id="owner-changed", status="bot")
        db.session.add(row)
        db.session.commit()
        conversation_id = row.id

    model_started = Event()
    finish_model = Event()

    def slow_model(*args, **kwargs):
        model_started.set()
        assert finish_model.wait(timeout=15)
        return _chat_result(need_human=False)

    def anonymous_chat():
        with app.test_client() as client:
            return client.post("/api/agents/chat/", headers={"X-Tenant-Slug": "test-a"},
                               json={"text": "访客问题", "session_id": "owner-changed"})

    with patch("flask_shop.agents.views.orchestrator.run_chat", side_effect=slow_model):
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(anonymous_chat)
            assert model_started.wait(timeout=10)
            try:
                with app.app_context(), tenant_context(disabled=True):
                    db.session.get(models.SupportConversation, conversation_id).customer_id = customer_id
                    db.session.commit()
            finally:
                finish_model.set()
            response = future.result(timeout=15)
    assert response.status_code == 403
    with app.app_context(), tenant_context(disabled=True):
        row = db.session.get(models.SupportConversation, conversation_id)
        assert row.customer_id == customer_id
        assert row.messages.count() == 0


def test_chat_does_not_return_ai_answer_if_timeline_cannot_be_saved(api):
    with patch("flask_shop.agents.views.orchestrator.run_chat", return_value=_chat_result(need_human=False)), \
         patch("flask_shop.agents.support.persist_agent_turn", side_effect=RuntimeError("database unavailable")):
        response = api["client"].post("/api/agents/chat/", headers={"X-Tenant-Slug": "test-a"},
                                      json={"text": "你好", "session_id": "timeline-failure"})
    assert response.status_code == 503
    assert "data" not in response.get_json()


@pytest.mark.parametrize('agent_name,text', [
    ('intent', '你好'), ('catalog', '有没有耳机'), ('risk', '你好'), ('cs', '你好'),
])
def test_failed_agent_transfers_customer_to_human_without_exposing_exception(api, app, agent_name, text):
    from flask_shop.agents.orchestrator import orchestrator

    secret = 'internal-secret-detail'
    with patch.object(getattr(orchestrator, agent_name), 'run', side_effect=RuntimeError(secret)):
        response = api['client'].post('/api/agents/chat/', headers={'X-Tenant-Slug': 'test-a'},
                                      json={'text': text, 'session_id': f'failure-{agent_name}'}).get_json()
    assert response['status'] == 200
    assert response['data']['need_human'] is True
    assert response['data']['support']['status'] == 'waiting'
    assert secret not in str(response)
    with app.app_context(), tenant_context(disabled=True):
        row = models.SupportConversation.query.filter_by(session_id=f'failure-{agent_name}').one()
        assert row.need_human == 1 and row.status == 'waiting'
        assert [message.content for message in row.messages.all()] == [text, response['data']['reply']]


@pytest.mark.parametrize('invalid_result', [None, {}, {'status': 500}, {'status': 200, 'data': {'reply': ''}}])
def test_invalid_ai_result_transfers_to_human(api, invalid_result):
    with patch('flask_shop.agents.views.orchestrator.run_chat', return_value=invalid_result):
        response = api['client'].post('/api/agents/chat/', headers={'X-Tenant-Slug': 'test-a'},
                                      json={'text': '需要帮助', 'session_id': 'invalid-ai'}).get_json()
    assert response['status'] == 200
    assert response['data']['need_human'] is True
    assert response['data']['support']['status'] == 'waiting'


def test_orchestrator_exception_transfers_to_human_and_records_message(api, app):
    with patch('flask_shop.agents.views.orchestrator.run_chat', side_effect=RuntimeError('internal-secret-detail')):
        response = api['client'].post('/api/agents/chat/', headers={'X-Tenant-Slug': 'test-a'},
                                      json={'text': '订单怎么处理', 'session_id': 'orchestrator-failure'}).get_json()
    assert response['status'] == 200
    assert response['data']['support']['status'] == 'waiting'
    assert 'internal-secret-detail' not in str(response)
    with app.app_context(), tenant_context(disabled=True):
        row = models.SupportConversation.query.filter_by(session_id='orchestrator-failure').one()
        assert row.messages.filter_by(sender_type='customer').one().content == '订单怎么处理'


def test_human_takeover_wins_when_ai_fails_during_generation(api, app):
    seed = api['seed']
    with app.app_context(), tenant_context(disabled=True):
        conversation = models.SupportConversation(tenant_id=seed['id_a'], session_id='failed-slow-ai', status='bot')
        db.session.add(conversation)
        db.session.commit()
        conversation_id = conversation.id
    started, finish = Event(), Event()

    def fail_after_takeover(*args, **kwargs):
        started.set()
        assert finish.wait(timeout=15)
        raise RuntimeError('AI failed')

    def chat():
        with app.test_client() as client:
            return client.post('/api/agents/chat/', headers={'X-Tenant-Slug': 'test-a'},
                               json={'text': '顾客原始问题', 'session_id': 'failed-slow-ai'}).get_json()

    with patch('flask_shop.agents.views.orchestrator.run_chat', side_effect=fail_after_takeover):
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(chat)
            assert started.wait(timeout=10)
            try:
                claimed = api['client'].post(f'/api/agents/support/conversations/{conversation_id}/claim/',
                                             headers={'token': seed['token_a']}).get_json()
                assert claimed['status'] == 200
            finally:
                finish.set()
            result = future.result(timeout=15)
    assert result['data']['support']['status'] == 'active'
    assert result['data']['agents_ran'] == ['support_queue']
    with app.app_context(), tenant_context(disabled=True):
        row = db.session.get(models.SupportConversation, conversation_id)
        assert row.messages.filter_by(sender_type='customer').one().content == '顾客原始问题'
        assert row.messages.filter_by(sender_type='ai').count() == 0


def test_failed_fallback_persistence_does_not_claim_handoff_succeeded(api):
    with patch('flask_shop.agents.views.orchestrator.run_chat', side_effect=RuntimeError('ai failed')), \
         patch('flask_shop.agents.support.persist_agent_turn', side_effect=RuntimeError('db failed')):
        response = api['client'].post('/api/agents/chat/', headers={'X-Tenant-Slug': 'test-a'},
                                      json={'text': '需要帮助', 'session_id': 'failed-fallback'})
    assert response.status_code == 503
    assert 'data' not in response.get_json()


def test_customer_can_restart_a_previously_resolved_session(api, app):
    from datetime import datetime

    seed = api["seed"]
    with app.app_context(), tenant_context(disabled=True):
        row = models.SupportConversation(tenant_id=seed["id_a"], session_id="restart-resolved", status="resolved",
                                         resolved_at=datetime.now(), satisfaction=5)
        db.session.add(row)
        db.session.commit()
    with patch("flask_shop.agents.views.orchestrator.run_chat", return_value=_chat_result(need_human=False)):
        response = api["client"].post("/api/agents/chat/", headers={"X-Tenant-Slug": "test-a"},
                                      json={"text": "新的问题", "session_id": "restart-resolved"}).get_json()
    assert response["status"] == 200
    assert response["data"]["support"]["status"] == "bot"
    assert response["data"]["support"]["satisfaction"] is None
