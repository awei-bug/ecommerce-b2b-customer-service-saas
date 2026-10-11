# -*- coding: utf-8 -*-
"""
本地/联调短信 HTTP 网关（模拟真实短信通道）。

协议（与 flask_shop SMS_PROVIDER=http 对齐）：
  POST /send
  Header: Authorization: Bearer <SMS_HTTP_TOKEN>  （可选）
  Body: {"phone":"13800138000","code":"123456","scene":"login"}
  Resp: {"ok": true, "msg": "sent", "id": "..."}

查询最近验证码（仅联调）：
  GET /inbox?phone=13800138000
  GET /health

默认监听 http://127.0.0.1:19090
"""
from __future__ import annotations

import json
import os
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock
from urllib.parse import parse_qs, urlparse

HOST = os.getenv("SMS_GW_HOST", "127.0.0.1")
PORT = int(os.getenv("SMS_GW_PORT", "19090"))
TOKEN = os.getenv("SMS_HTTP_TOKEN", "dev-sms-token")
LOG_FILE = Path(os.getenv("SMS_GW_LOG", str(Path(__file__).resolve().parents[1] / "backups" / "sms_gateway_inbox.jsonl")))

_lock = Lock()
_inbox = []  # newest first, max 200


def _auth_ok(handler: BaseHTTPRequestHandler) -> bool:
    if not TOKEN:
        return True
    auth = handler.headers.get("Authorization") or ""
    if auth == f"Bearer {TOKEN}":
        return True
    if handler.headers.get("X-SMS-Token") == TOKEN:
        return True
    return False


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print("[sms-gw]", fmt % args)

    def _json(self, code: int, obj: dict):
        raw = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path in ("/health", "/health/"):
            return self._json(200, {"ok": True, "service": "sms-http-gateway", "inbox": len(_inbox)})
        if u.path in ("/inbox", "/inbox/"):
            if not _auth_ok(self):
                return self._json(401, {"ok": False, "msg": "unauthorized"})
            qs = parse_qs(u.query or "")
            phone = (qs.get("phone") or [""])[0].strip()
            with _lock:
                rows = list(_inbox)
            if phone:
                rows = [r for r in rows if r.get("phone") == phone]
            return self._json(200, {"ok": True, "data": rows[:20]})
        return self._json(404, {"ok": False, "msg": "not found"})

    def do_POST(self):
        u = urlparse(self.path)
        if u.path not in ("/send", "/send/"):
            return self._json(404, {"ok": False, "msg": "not found"})
        if not _auth_ok(self):
            return self._json(401, {"ok": False, "msg": "unauthorized"})
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b"{}"
        try:
            body = json.loads(raw.decode("utf-8"))
        except Exception:
            return self._json(400, {"ok": False, "msg": "invalid json"})
        phone = str(body.get("phone") or "").strip()
        code = str(body.get("code") or "").strip()
        scene = str(body.get("scene") or "login").strip()
        if not phone or not code:
            return self._json(400, {"ok": False, "msg": "phone/code required"})
        item = {
            "id": uuid.uuid4().hex,
            "ts": time.time(),
            "phone": phone,
            "code": code,
            "scene": scene,
            "text": f"【云购商城】您的登录验证码是 {code}，10分钟内有效。",
        }
        with _lock:
            _inbox.insert(0, item)
            del _inbox[200:]
        try:
            LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
            with LOG_FILE.open("a", encoding="utf-8") as f:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
        except Exception as e:
            print("[sms-gw] log fail", e)
        print(f"[sms-gw] SENT phone={phone} code={code} scene={scene}")
        return self._json(200, {"ok": True, "msg": "sent", "id": item["id"]})


def main():
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    print("=" * 56)
    print(" SMS HTTP Gateway (local)")
    print(f" POST http://{HOST}:{PORT}/send")
    print(f" GET  http://{HOST}:{PORT}/inbox?phone=1xxxxxxxxxx")
    print(f" token: Bearer {TOKEN}")
    print(f" log: {LOG_FILE}")
    print("=" * 56)
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
