# -*- coding: utf-8 -*-
"""端到端：SMS_DEV_MODE=0 + HTTP 网关 发码→读 inbox→登录。"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

# force prod-like sms for this process
os.environ.pop("DATABASE_URL", None)
os.environ["SMS_DEV_MODE"] = "0"
os.environ["SMS_PROVIDER"] = "http"
os.environ["SMS_HTTP_URL"] = os.getenv("SMS_HTTP_URL") or "http://127.0.0.1:19090/send"
os.environ["SMS_HTTP_TOKEN"] = os.getenv("SMS_HTTP_TOKEN") or "dev-sms-token"
os.environ["SMS_DEV_COOLDOWN"] = "1"
os.environ["SMS_COOLDOWN"] = "1"

from dotenv import load_dotenv
load_dotenv(ROOT / ".env", override=False)
# keep forced sms overrides
os.environ["SMS_DEV_MODE"] = "0"
os.environ["SMS_PROVIDER"] = "http"
os.environ["SMS_HTTP_URL"] = os.environ.get("SMS_HTTP_URL") or "http://127.0.0.1:19090/send"
os.environ["SMS_HTTP_TOKEN"] = os.environ.get("SMS_HTTP_TOKEN") or "dev-sms-token"

from flask_shop import create_app


def http_get(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode())


def main():
    # gateway health
    try:
        h = http_get("http://127.0.0.1:19090/health")
        print("gateway", h)
    except Exception as e:
        print("FAIL: 请先启动网关 deploy/win/start_sms_gateway.bat")
        print(e)
        return 1

    app = create_app(os.getenv("FLASK_CONFIG") or "develop")
    c = app.test_client()
    phone = "13800139876"
    r = c.post(
        "/api/c/auth/sms/send/",
        json={"phone": phone},
        headers={"X-Tenant-Slug": "demo"},
    ).get_json()
    print("send", r)
    if r.get("status") != 200:
        return 1
    if r.get("data", {}).get("dev_code"):
        print("WARN: still returning dev_code (SMS_DEV_MODE may still be on)")
    # read inbox
    req = urllib.request.Request(
        f"http://127.0.0.1:19090/inbox?phone={phone}",
        headers={"Authorization": f"Bearer {os.environ['SMS_HTTP_TOKEN']}"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        inbox = json.loads(resp.read().decode())
    print("inbox", inbox)
    rows = inbox.get("data") or []
    if not rows:
        print("FAIL no inbox")
        return 1
    code = rows[0]["code"]
    r2 = c.post(
        "/api/c/auth/sms/login/",
        json={"phone": phone, "code": code, "nickname": "短信网关测试"},
        headers={"X-Tenant-Slug": "demo"},
    ).get_json()
    print("login", r2.get("status"), r2.get("msg"), bool((r2.get("data") or {}).get("token")))
    if r2.get("status") != 200:
        return 1
    print("SMS_HTTP_E2E_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
