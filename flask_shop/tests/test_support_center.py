from unittest.mock import patch

from flask_shop import db, models
from flask_shop.utils.token import generate_token
from flask_shop.utils.tenant_query import tenant_context


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
