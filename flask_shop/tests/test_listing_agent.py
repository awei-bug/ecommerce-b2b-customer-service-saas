# -*- coding: utf-8 -*-
import os
os.environ["AGENTS_LLM"] = "0"

import pytest

from flask_shop import db, models
from flask_shop.agents.listing import parse_listing_draft
from flask_shop.agents.orchestrator import orchestrator
from flask_shop.utils.tenant_query import tenant_context


def test_parse_listing_draft_extracts_fields():
    d = parse_listing_draft("上架纯棉T恤，89元，库存30")
    assert d["name"] == "纯棉T恤"
    assert d["price"] == 89
    assert d["stock"] == 30
    assert d["missing"] == []


def test_parse_listing_draft_requires_price():
    d = parse_listing_draft("上架台灯")
    assert "price" in d["missing"]
    assert d["name"] == "台灯"


def test_admin_ops_lists_product(app, monkeypatch):
    seed = app._seed_ctx
    import flask_shop.agents.content_agent as content_agent

    monkeypatch.setattr(content_agent, "llm_enabled", lambda: True)
    monkeypatch.setattr(
        content_agent,
        "chat_completions",
        lambda *_args, **_kwargs: pytest.fail("quick listing must not wait for the external LLM"),
    )
    with app.app_context(), tenant_context(disabled=True):
        before = models.Product.query.filter_by(tenant_id=seed["id_a"]).count()
        r = orchestrator.run_chat(
            "上架纯棉T恤，89元，库存30",
            tenant_slug="test-a",
            tenant_id=seed["id_a"],
            channel="admin_ops",
        )
        data = r["data"]
        assert "已上架" in (data.get("reply") or ""), data.get("reply")
        assert (data.get("intent") or {}).get("intent") == "list_product"
        listing = (data.get("ops") or {}).get("listing") or {}
        assert listing.get("applied") is True
        pid = listing.get("product_id")
        assert pid
        p = db.session.get(models.Product, pid)
        assert p is not None
        assert p.tenant_id == seed["id_a"]
        assert int(p.state or 0) == 2
        assert float(p.price) == 89
        assert int(p.number or 0) == 30
        assert "品质精选" in (p.introduce or "")
        after = models.Product.query.filter_by(tenant_id=seed["id_a"]).count()
        assert after == before + 1
        paths = [str(a.get("path") or "") for a in (data.get("actions") or [])]
        assert any("/product_list" in x for x in paths)


def test_admin_ops_missing_price_does_not_write(app):
    seed = app._seed_ctx
    with app.app_context(), tenant_context(disabled=True):
        before = models.Product.query.filter_by(tenant_id=seed["id_a"]).count()
        r = orchestrator.run_chat(
            "上架台灯",
            tenant_slug="test-a",
            tenant_id=seed["id_a"],
            channel="admin_ops",
        )
        assert "售价" in (r["data"].get("reply") or "")
        after = models.Product.query.filter_by(tenant_id=seed["id_a"]).count()
        assert after == before
        listing = (r["data"].get("ops") or {}).get("listing") or {}
        assert listing.get("applied") is not True


def test_mall_chat_cannot_list_product(app):
    seed = app._seed_ctx
    with app.app_context(), tenant_context(disabled=True):
        before = models.Product.query.filter_by(tenant_id=seed["id_a"]).count()
        r = orchestrator.run_chat(
            "上架纯棉T恤，89元，库存30",
            tenant_slug="test-a",
            tenant_id=seed["id_a"],
            channel="mall_chat",
        )
        after = models.Product.query.filter_by(tenant_id=seed["id_a"]).count()
        assert after == before
        reply = r["data"].get("reply") or ""
        assert "后台" in reply or "不能改商品库" in reply
        assert (r["data"].get("intent") or {}).get("blocked_listing") is True
