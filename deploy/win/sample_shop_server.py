# -*- coding: utf-8 -*-
"""本机样板店单入口：商城 + 后台 + API，默认 http://127.0.0.1:18080"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FLASK_SHOP = ROOT / "flask_shop"
MALL_DIST = ROOT / "mall" / "dist"
ADMIN_DIST = ROOT / "vue_shop" / "dist"

sys.path.insert(0, str(FLASK_SHOP))
os.chdir(FLASK_SHOP)


def _load_env_prod():
    env_path = ROOT / "deploy" / ".env.prod"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip()
        if k in (
            "FLASK_CONFIG",
            "DATABASE_URL",
            "ALLOW_MOCK_PAY",
            "SMS_DEV_MODE",
            "PUBLIC_BASE_URL",
            "CORS_ORIGINS",
            "PRIVATE_DEPLOY",
            "MYSQL_HOST",
            "MYSQL_PORT",
            "MYSQL_USERNAME",
            "MYSQL_PASSWORD",
            "MYSQL_DB",
            "MYSQL_ROOT_PASSWORD",
        ):
            continue
        os.environ.setdefault(k, v)


_load_env_prod()

# 数据库：优先 flask_shop/.env 的 MySQL；否则 SQLite 样板库
os.environ.pop("DATABASE_URL", None)
try:
    from dotenv import load_dotenv
    load_dotenv(FLASK_SHOP / ".env", override=True)
except Exception:
    pass

db_path = FLASK_SHOP / "instance" / "sample_shop.db"
db_path.parent.mkdir(parents=True, exist_ok=True)

mysql_host = (os.getenv("MYSQL_HOST") or "").strip()
mysql_db = (os.getenv("MYSQL_DB") or "").strip()
if mysql_host and mysql_db and not (os.getenv("DATABASE_URL") or "").strip():
    DB_URI = None
    db_label = f"mysql://{os.getenv('MYSQL_USERNAME')}:{os.getenv('MYSQL_HOST')}:{os.getenv('MYSQL_PORT')}/{mysql_db}"
else:
    DB_URI = "sqlite:///" + str(db_path.resolve()).as_posix()
    os.environ["DATABASE_URL"] = DB_URI
    db_label = DB_URI

os.environ["FLASK_CONFIG"] = "sample"
os.environ["PRIVATE_DEPLOY"] = "1"
os.environ["ALLOW_MOCK_PAY"] = os.getenv("ALLOW_MOCK_PAY") or "0"
os.environ["SMS_DEV_MODE"] = os.getenv("SMS_DEV_MODE") or "1"
os.environ["PAY_DEFAULT_CHANNEL"] = "mock"
os.environ["PUBLIC_BASE_URL"] = os.getenv("PUBLIC_BASE_URL") or "http://127.0.0.1:18080"
os.environ.setdefault("CORS_ORIGINS", "http://127.0.0.1:18080,http://localhost:18080")

from flask import Flask, request, send_from_directory
from werkzeug.middleware.dispatcher import DispatcherMiddleware

from flask_shop import create_app, db, models
from flask_shop.utils.tenant_query import tenant_context

api_app = create_app("sample")


@api_app.after_request
def _no_cache_spa(resp):
    """改完 dist 后刷新即可生效，减少强缓存导致的「改了没变化」。"""
    try:
        path = (request.path or "").lower()
    except Exception:
        path = ""
    if path.endswith((".html", ".js", ".css")) or path in ("/", "/admin", "/admin/"):
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        resp.headers["Pragma"] = "no-cache"
        resp.headers["Expires"] = "0"
    return resp



def _run_seed_scripts():
    """子进程灌库，避免 seed_shop 模块内 create_app('develop') 连错库。"""
    py = str(FLASK_SHOP / ".venv" / "Scripts" / "python.exe")
    env = os.environ.copy()
    if DB_URI:
        env["DATABASE_URL"] = DB_URI
    else:
        env.pop("DATABASE_URL", None)
    env["FLASK_CONFIG"] = "develop"
    env["ALLOW_DB_RESET"] = "0"
    for script in ("seed_shop.py", "seed_product_images.py"):
        sp = FLASK_SHOP / "scripts" / script
        if not sp.exists():
            print("[sample] skip missing", script)
            continue
        print("[sample] run", script)
        # patch: seed_shop creates develop app - DATABASE_URL must be set before import
        r = subprocess.run(
            [py, str(sp)] + ([] if script != "seed_shop.py" else []),
            cwd=str(FLASK_SHOP),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        print((r.stdout or "")[-800:].encode("ascii", "replace").decode("ascii"))
        if r.returncode != 0:
            print((r.stderr or "")[-800:].encode("ascii", "replace").decode("ascii"))
            print("[sample] warn:", script, "exit", r.returncode)


def bootstrap():
    with api_app.app_context():
        db.create_all()
        with tenant_context(disabled=True):
            has = models.Tenant.query.filter_by(slug="demo").first() is not None
        if has:
            print("[sample] demo tenant exists")
            # ensure images if products lack covers
            with tenant_context(disabled=True):
                bare = models.Product.query.filter(
                    (models.Product.big_img.is_(None)) | (models.Product.big_img == "")
                ).count()
            if bare:
                print("[sample] products missing images:", bare)
                _run_seed_scripts()
            return
    print("[sample] first boot — seeding sample_shop.db ...")
    _run_seed_scripts()


bootstrap()

admin_app = Flask("admin_spa", static_folder=None)


@admin_app.route("/", defaults={"path": ""})
@admin_app.route("/<path:path>")
def admin_spa(path: str):
    if not ADMIN_DIST.exists():
        return ("vue_shop/dist missing; build with publicPath=/admin/", 500)
    if path:
        fp = ADMIN_DIST / path
        if fp.is_file():
            return send_from_directory(ADMIN_DIST, path)
    return send_from_directory(ADMIN_DIST, "index.html")


@api_app.route("/", defaults={"spa_path": ""})
@api_app.route("/<path:spa_path>")
def mall_spa(spa_path: str):
    if not MALL_DIST.exists():
        return ("mall/dist missing; run npm run build in mall/", 500)
    if spa_path:
        fp = MALL_DIST / spa_path
        if fp.is_file():
            return send_from_directory(MALL_DIST, spa_path)
    return send_from_directory(MALL_DIST, "index.html")


application = DispatcherMiddleware(api_app, {"/admin": admin_app})


def main():
    host = os.environ.get("SAMPLE_HOST", "127.0.0.1")
    port = int(os.environ.get("SAMPLE_PORT", "18080"))
    print("=" * 60)
    print("  云购商城 · 本机样板店")
    print(f"  商城  http://{host}:{port}/")
    print(f"  后台  http://{host}:{port}/admin/")
    print(f"  健康  http://{host}:{port}/health/")
    print("  店长  团队 demo / admin / 123456")
    print("  顾客  手机号 + 页面验证码（样板开启 SMS_DEV）")
    print(f"  数据库 {db_label}")
    print("=" * 60)
    try:
        from waitress import serve

        serve(application, host=host, port=port, threads=8)
    except ImportError:
        from werkzeug.serving import run_simple

        run_simple(host, port, application, use_debugger=False, use_reloader=False)


if __name__ == "__main__":
    main()