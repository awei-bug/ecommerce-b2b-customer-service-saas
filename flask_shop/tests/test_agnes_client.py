# -*- coding: utf-8 -*-
from flask_shop.agents.tools import agnes_client


def test_agnes_image_request_normalizes_url(monkeypatch):
    captured = {}

    def fake_request(method, url, *, body=None, timeout=0, query=None):
        captured.update(method=method, url=url, body=body, timeout=timeout)
        return {"ok": True, "data": {"model": "agnes-image-2.5-flash", "data": [{"url": "https://cdn.test/a.png"}]}}

    monkeypatch.setenv("AGNES_API_KEY", "test-key")
    monkeypatch.setattr(agnes_client, "_request", fake_request)
    result = agnes_client.generate_image("white product photo", size="2K", ratio="4:3")

    assert result["ok"] is True
    assert result["url"] == "https://cdn.test/a.png"
    assert captured["url"].endswith("/images/generations")
    assert captured["body"]["model"] == "agnes-image-2.5-flash"
    assert captured["body"]["extra_body"]["response_format"] == "url"


def test_agnes_video_request_returns_async_id(monkeypatch):
    monkeypatch.setenv("AGNES_API_KEY", "test-key")
    monkeypatch.setattr(
        agnes_client,
        "_request",
        lambda *args, **kwargs: {"ok": True, "data": {"video_id": "video_123", "status": "queued"}},
    )

    result = agnes_client.create_video("slow product rotation", aspect_ratio="9:16")

    assert result["ok"] is True
    assert result["video_id"] == "video_123"
    assert result["status"] == "queued"


def test_agnes_is_disabled_without_key(monkeypatch):
    monkeypatch.delenv("AGNES_API_KEY", raising=False)
    monkeypatch.delenv("AGNESAI_API_KEY", raising=False)
    assert agnes_client.enabled() is False
    assert agnes_client.generate_image("anything")["error"] == "missing_agnes_api_key"
