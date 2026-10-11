# -*- coding: utf-8 -*-
"""数据中心客户端：电商侧拉取商品知识、回执上架结果。

数据中心是权威，电商库是消费副本。所有网络异常只影响同步，不影响商城主流程。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import requests
from flask import current_app

log = logging.getLogger(__name__)


class HubError(RuntimeError):
    """数据中心不可用或返回错误。"""


def hub_enabled() -> bool:
    try:
        return bool(current_app.config.get("DATA_HUB_URL"))
    except Exception:
        return False


def _config() -> Dict[str, Any]:
    cfg = current_app.config
    return {
        "url": (cfg.get("DATA_HUB_URL") or "").rstrip("/"),
        "token": cfg.get("DATA_HUB_TOKEN") or "",
        "slug": cfg.get("DATA_HUB_TENANT_SLUG") or "",
        "timeout": int(cfg.get("DATA_HUB_TIMEOUT") or 10),
    }


def _headers() -> Dict[str, str]:
    cfg = _config()
    headers = {"Content-Type": "application/json"}
    if cfg["slug"]:
        headers["X-Hub-Tenant"] = cfg["slug"]
    if cfg["token"]:
        headers["X-Hub-Token"] = cfg["token"]
    return headers


def _request(method: str, path: str, body: Optional[dict] = None, timeout: Optional[int] = None) -> dict:
    cfg = _config()
    if not cfg["url"]:
        raise HubError("未配置 DATA_HUB_URL")
    url = f"{cfg['url']}{path}"
    try:
        resp = requests.request(
            method,
            url,
            json=body,
            headers=_headers(),
            timeout=timeout or cfg["timeout"],
        )
    except Exception as exc:
        raise HubError(f"数据中心连接失败：{exc}") from exc

    try:
        payload = resp.json()
    except Exception:
        payload = {}

    if resp.status_code >= 400:
        raise HubError(payload.get("error") or payload.get("message") or f"数据中心返回 {resp.status_code}")
    return payload


def health() -> dict:
    return _request("GET", "/health", timeout=5)


def fetch_products(status: str = "", since: str = "", limit: int = 50) -> List[dict]:
    """拉取数据中心商品。since 为 ISO 时间串，用于增量同步。"""
    cfg = _config()
    params = f"tenant={cfg['slug']}&limit={int(limit)}"
    if status:
        params += f"&status={status}"
    if since:
        params += f"&since={since}"
    payload = _request("GET", f"/hub/products?{params}")
    return payload.get("items") or []


def fetch_product(external_id: str) -> Optional[dict]:
    cfg = _config()
    payload = _request("GET", f"/hub/products/{cfg['slug']}/{external_id}")
    return payload.get("item")


def search(query: str, limit: int = 5, published_only: bool = True) -> List[dict]:
    """客服检索：返回结构化知识卡。"""
    cfg = _config()
    payload = _request("POST", "/hub/search", {
        "tenant_slug": cfg["slug"],
        "query": query,
        "limit": int(limit),
        "published_only": bool(published_only),
    })
    return payload.get("cards") or []


def ack(external_id: str, product_id: Optional[int], status: str = "published") -> dict:
    cfg = _config()
    return _request(
        "POST",
        f"/hub/products/{cfg['slug']}/{external_id}/ack",
        {"product_id": product_id, "status": status},
    )
