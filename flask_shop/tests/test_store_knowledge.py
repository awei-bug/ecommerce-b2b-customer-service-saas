import io
from unittest.mock import patch

from flask_shop import db, models
from flask_shop.agents import knowledge
from flask_shop.utils.tenant_query import tenant_context


def _headers(seed, tenant="a"):
    return {"token": seed[f"token_{tenant}"]}


def test_store_knowledge_crud_is_tenant_scoped_and_audited(api, app):
    client = api["client"]
    seed = api["seed"]
    created = client.post(
        "/api/agents/knowledge/",
        headers=_headers(seed),
        json={
            "title": "A-发货规则",
            "category": "shipping",
            "question": "多久发货",
            "content": "确认收款后 48 小时内发货。",
            "keywords": ["发货", "时效"],
            "status": "published",
            "priority": 70,
        },
    ).get_json()
    assert created["status"] == 200
    knowledge_id = created["data"]["id"]

    own_list = client.get("/api/agents/knowledge/", headers=_headers(seed)).get_json()
    assert [item["title"] for item in own_list["data"]["items"]] == ["A-发货规则"]
    assert own_list["data"]["counts"]["published"] == 1

    other_list = client.get("/api/agents/knowledge/", headers=_headers(seed, "b")).get_json()
    assert other_list["data"]["items"] == []
    other_update = client.put(
        f"/api/agents/knowledge/{knowledge_id}/",
        headers=_headers(seed, "b"),
        json={"title": "越权", "content": "不能成功", "status": "published"},
    ).get_json()
    assert other_update["status"] == 404

    updated = client.put(
        f"/api/agents/knowledge/{knowledge_id}/",
        headers=_headers(seed),
        json={
            "title": "A-发货规则",
            "category": "shipping",
            "content": "确认收款后 24 小时内发货。",
            "keywords": "发货;配送",
            "status": "published",
            "priority": 80,
        },
    ).get_json()
    assert updated["status"] == 200
    assert updated["data"]["keywords"] == ["发货", "配送"]

    deleted = client.delete(f"/api/agents/knowledge/{knowledge_id}/", headers=_headers(seed)).get_json()
    assert deleted["status"] == 200
    with app.app_context(), tenant_context(disabled=True):
        actions = {row.action for row in models.AuditLog.query.filter_by(tenant_id=seed["id_a"]).all()}
        assert {"knowledge.create", "knowledge.update", "knowledge.delete"}.issubset(actions)


def test_draft_is_not_retrieved_and_published_entry_returns_citation(api, app):
    seed = api["seed"]
    with app.app_context(), tenant_context(disabled=True):
        draft = models.StoreKnowledge(
            tenant_id=seed["id_a"],
            title="发票草稿",
            category="payment",
            question="可以开发票吗",
            content="这是尚未发布的规则。",
            status="draft",
            priority=100,
        )
        draft.set_keywords(["发票", "开票"])
        published = models.StoreKnowledge(
            tenant_id=seed["id_a"],
            title="发货时效",
            category="shipping",
            question="多久发货",
            content="付款确认后 48 小时内发出。",
            status="published",
            priority=80,
        )
        published.set_keywords(["发货", "配送"])
        db.session.add_all([draft, published])
        db.session.commit()
        published_id = published.id

        with patch("flask_shop.utils.hub_client.hub_enabled", return_value=False):
            assert knowledge.load_knowledge(seed["id_a"], "发票怎么开") == []
            cards = knowledge.load_knowledge(seed["id_a"], "多久发货")
        assert cards[0]["citation_id"] == f"KB-{published_id}"

    with patch("flask_shop.agents.cs_agent.llm_enabled", return_value=False), patch(
        "flask_shop.utils.hub_client.hub_enabled", return_value=False
    ):
        response = api["client"].post(
            "/api/agents/chat/",
            headers={"X-Tenant-Slug": "test-a"},
            json={"text": "你们多久发货", "session_id": "knowledge-hit"},
        ).get_json()
    assert response["status"] == 200
    assert response["data"]["need_human"] is False
    assert response["data"]["citations"] == [{
        "id": f"KB-{published_id}",
        "title": "发货时效",
        "category": "shipping",
        "source": "商家知识库",
    }]
    assert "48 小时" in response["data"]["reply"]


def test_policy_miss_handoffs_but_greeting_stays_with_ai(api, app):
    client = api["client"]
    with patch("flask_shop.agents.cs_agent.llm_enabled", return_value=False), patch(
        "flask_shop.utils.hub_client.hub_enabled", return_value=False
    ):
        missed = client.post(
            "/api/agents/chat/",
            headers={"X-Tenant-Slug": "test-b"},
            json={"text": "你们可以开发票吗", "session_id": "knowledge-miss"},
        ).get_json()
        greeting = client.post(
            "/api/agents/chat/",
            headers={"X-Tenant-Slug": "test-b"},
            json={"text": "你好", "session_id": "knowledge-greeting"},
        ).get_json()

    assert missed["data"]["need_human"] is True
    assert missed["data"]["citations"] == []
    assert "没有找到已确认的店铺规则" in missed["data"]["reply"]
    assert missed["data"]["support"]["status"] == "waiting"
    assert greeting["data"]["need_human"] is False
    assert greeting["data"]["support"]["status"] == "bot"

    with app.app_context(), tenant_context(disabled=True):
        row = models.SupportConversation.query.filter_by(
            tenant_id=api["seed"]["id_b"], session_id="knowledge-miss"
        ).first()
        ai_message = row.messages.filter_by(sender_type="ai").first()
        assert row.status == "waiting"
        assert ai_message.to_dict()["extra"]["citations"] == []


def test_store_knowledge_csv_import_reports_bad_rows(api, app):
    csv_data = (
        "title,category,question,content,keywords,status,priority\n"
        "付款说明,payment,怎么付款,扫码后备注订单号,付款;扫码,published,90\n"
        "错误行,unknown,,内容,,published,0\n"
    ).encode("utf-8-sig")
    body = api["client"].post(
        "/api/agents/knowledge/import/",
        headers=_headers(api["seed"]),
        data={"file": (io.BytesIO(csv_data), "knowledge.csv")},
        content_type="multipart/form-data",
    ).get_json()
    assert body["status"] == 200
    assert body["data"]["created"] == 1
    assert body["data"]["error_count"] == 1
    assert body["data"]["errors"][0]["row"] == 3

    with app.app_context(), tenant_context(disabled=True):
        row = models.StoreKnowledge.query.filter_by(tenant_id=api["seed"]["id_a"], title="付款说明").first()
        assert row is not None
        assert row.status == "published"
