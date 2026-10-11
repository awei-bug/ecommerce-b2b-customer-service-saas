# -*- coding: utf-8 -*-
"""导购入口：登录引导、立即购买 buy=1、后台待办队列。"""
import os
os.environ["AGENTS_LLM"] = "0"

import pytest

from flask_shop import db, models
from flask_shop.agents.orchestrator import orchestrator


def test_guest_order_query_asks_login(app):
    seed = app._seed_ctx
    with app.app_context():
        r = orchestrator.run_chat(
            "查订单",
            tenant_slug="test-a",
            tenant_id=seed["id_a"],
            channel="mall_chat",
        )
    data = r["data"]
    assert data.get("login_required") is True
    actions = data.get("actions") or []
    paths = [str(a.get("path") or "") for a in actions]
    assert any(p.startswith("/login") for p in paths)
    assert any("redirect=/orders" in p for p in paths)
    assert any(a.get("type") == "login" for a in actions)


def test_search_unique_product_buy_path(app):
    seed = app._seed_ctx
    with app.app_context():
        p = db.session.get(models.Product, seed["product_a"].id)
        p.number = 10
        db.session.commit()
        r = orchestrator.run_chat(
            "有没有唯一商品",
            tenant_slug="test-a",
            tenant_id=seed["id_a"],
            channel="mall_chat",
        )
    data = r["data"]
    draft = data.get("draft_order_hint") or {}
    actions = data.get("actions") or []
    paths = [str(draft.get("path") or "")] + [str(a.get("path") or "") for a in actions]
    assert any("/product/" in p and "?buy=1" in p for p in paths), paths
    products = data.get("products") or []
    assert any("唯一商品" in str(x.get("name") or "") for x in products) or any(
        "唯一商品" in str(draft.get("name") or "") for _ in [0]
    )


def test_admin_ops_queues_and_actions(app, monkeypatch):
    seed = app._seed_ctx
    import flask_shop.agents.intent_agent as intent_module

    monkeypatch.setattr(intent_module, "llm_enabled", lambda: True)
    monkeypatch.setattr(
        orchestrator.intent,
        "_refine_with_llm",
        lambda *_args, **_kwargs: pytest.fail("admin ops must not call the external LLM"),
    )
    monkeypatch.setattr(
        orchestrator.cs,
        "safe_run",
        lambda *_args, **_kwargs: pytest.fail("admin ops must not run CS polishing"),
    )
    with app.app_context():
        r = orchestrator.run_chat(
            "待发货订单",
            tenant_slug="test-a",
            tenant_id=seed["id_a"],
            channel="admin_ops",
        )
    data = r["data"]
    assert (data.get("intent") or {}).get("intent") == "ops"
    assert (data.get("intent") or {}).get("llm") == {"used": False}
    assert "cs" not in (data.get("agents_ran") or [])
    ops = data.get("ops") or {}
    queues = ops.get("queues") or {}
    assert "pending_pay" in queues
    assert any(o.get("order_no") == "A-ORD-1" for o in (queues.get("pending_pay") or []))
    actions = data.get("actions") or ops.get("actions") or []
    assert any(a.get("type") == "ops_queue" for a in actions)
    assert any("pending_pay" in str(a.get("path") or "") for a in actions)


def test_guide_product_price_matches_c_api(api, app):
    seed = api["seed"]
    p = db.session.get(models.Product, seed["product_a"].id)
    p.number = 10
    p.price = 88.5
    p.state = 2
    db.session.commit()
    pid = p.id
    name = p.name
    r = orchestrator.run_chat(
        "有没有唯一商品",
        tenant_slug="test-a",
        tenant_id=seed["id_a"],
        channel="mall_chat",
    )
    data = r["data"]
    products = data.get("products") or []
    hit = next((x for x in products if x.get("id") == pid), None)
    assert hit, products
    assert float(hit["price"]) == 88.5
    assert hit.get("name") == name
    assert any(
        f"/product/{pid}" in str(a.get("path") or "")
        for a in (data.get("actions") or [])
    ) or f"/product/{pid}" in str((data.get("draft_order_hint") or {}).get("path") or "")
    detail = api["client"].get(
        f"/api/c/product/{pid}/",
        headers={"X-Tenant-Slug": "test-a"},
    ).get_json()
    assert detail["status"] == 200, detail
    assert float(detail["data"]["price"]) == float(hit["price"])
    assert detail["data"]["name"] == hit["name"]

