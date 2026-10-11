# -*- coding: utf-8 -*-
"""v1 上线/样板检查：库连接、密钥、演示密码、商品与付款配置。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
os.environ.pop("DATABASE_URL", None)  # 尊重 .env MySQL

from dotenv import load_dotenv

load_dotenv(ROOT / ".env", override=True)

from flask_shop import create_app, models
from flask_shop.utils.tenant_query import tenant_context


def main():
    cfg_name = os.getenv("FLASK_CONFIG") or "develop"
    app = create_app(cfg_name)
    print("=" * 56)
    print("v1 go-live check")
    print("=" * 56)
    uri = app.config.get("SQLALCHEMY_DATABASE_URI") or ""
    safe = uri
    if "@" in safe and "://" in safe:
        # hide password
        try:
            head, rest = safe.split("://", 1)
            cred, host = rest.split("@", 1)
            user = cred.split(":")[0]
            safe = f"{head}://{user}:***@{host}"
        except Exception:
            pass
    print(f"config: {cfg_name}")
    print(f"db:     {safe}")
    print(f"mock:   ALLOW_MOCK_PAY={app.config.get('ALLOW_MOCK_PAY')}")
    print(f"sms:    SMS_DEV_MODE={app.config.get('SMS_DEV_MODE')}")

    fails = []
    warns = []

    if "sqlite" in uri.lower():
        warns.append("当前为 SQLite；正式交付建议 MySQL")
    if "3306" in uri and "3307" not in uri:
        pass
    secret = app.config.get("SECRET_KEY") or ""
    if len(secret) < 32 or secret in getattr(
        __import__("config", fromlist=["Config"]).Config, "WEAK_SECRETS", set()
    ):
        fails.append("SECRET_KEY 过弱或过短")

    with app.app_context():
        with tenant_context(disabled=True):
            t = models.Tenant.query.filter_by(slug="demo").first()
            if not t:
                fails.append("缺少 demo 租户，请先 seed")
            else:
                print(f"tenant: {t.name} (id={t.id})")
                if not (t.pay_guide or "").strip():
                    warns.append("未配置 pay_guide 付款说明")
                if not getattr(t, "pay_qr_wechat", None) and not getattr(t, "pay_qr_alipay", None):
                    warns.append("未上传个人收款码（店铺设置）")
                n = models.Product.query.filter_by(tenant_id=t.id).count()
                print(f"products: {n}")
                if n < 1:
                    fails.append("没有商品")
                bare = models.Product.query.filter(
                    models.Product.tenant_id == t.id,
                    (models.Product.big_img.is_(None)) | (models.Product.big_img == ""),
                ).count()
                if bare:
                    warns.append(f"{bare} 个商品无主图")
                admin = models.User.query.filter_by(tenant_id=t.id, name="admin").first()
                if admin and admin.check_password("123456"):
                    warns.append("admin 仍为默认密码 123456，上线前请修改")

    print("-" * 56)
    if fails:
        print("FAIL:")
        for x in fails:
            print("  -", x)
    if warns:
        print("WARN:")
        for x in warns:
            print("  -", x)
    if not fails and not warns:
        print("PASS: 无阻断项")
    elif not fails:
        print("PASS_WITH_WARNINGS: 可演示，正式对外前处理 WARN")
    else:
        print("BLOCKED: 请先处理 FAIL")
        return 1
    print("=" * 56)
    print("下一步人工项:")
    print("  1) 后台店铺设置上传微信/支付宝收款码")
    print("  2) 修改 admin 密码（接口 POST /user/change-password/）")
    print("  3) 正式环境关 SMS_DEV_MODE，配置 HTTPS/域名")
    print("  4) 定期执行 deploy/win/backup_mysql_local.bat")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
