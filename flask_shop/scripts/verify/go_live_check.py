# -*- coding: utf-8 -*-
"""v1 上线/样板检查：库连接、密钥、演示密码、商品与付款配置。"""
from __future__ import annotations

import os
import argparse
import re
import sys
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

ROOT = Path(__file__).resolve().parents[2]


def database_summary(uri):
    try:
        url = make_url(uri)
    except (ArgumentError, TypeError, ValueError):
        return '<invalid database URL>'
    if url.get_backend_name() == 'sqlite':
        return 'sqlite (path hidden)'
    host = url.host or 'local socket'
    database = url.database or '(missing database)'
    if not re.fullmatch(r'[A-Za-z0-9.:-]+', host):
        host = '<redacted>'
    if not re.fullmatch(r'[A-Za-z0-9_.-]+', database):
        database = '<redacted>'
    port = f':{url.port}' if url.port else ''
    return f'{url.drivername}://{host}{port}/{database}'


def main():
    parser = argparse.ArgumentParser(description='检查指定店铺的交付准备情况')
    parser.add_argument('--tenant', default=os.getenv('GO_LIVE_TENANT_SLUG', ''), help='待检查的店铺标识')
    args = parser.parse_args()
    os.chdir(ROOT)
    load_dotenv(ROOT / '.env', override=False)
    cfg_name = (os.getenv("FLASK_CONFIG") or "develop").strip().lower()
    tenant_slug = args.tenant or os.getenv('GO_LIVE_TENANT_SLUG', '')
    if not tenant_slug and cfg_name == 'product':
        print('生产检查必须使用 --tenant 指定真实店铺标识')
        return 1
    tenant_slug = tenant_slug or 'demo'
    if os.getenv('DATABASE_URL'):
        try:
            make_url(os.environ['DATABASE_URL'])
        except (ArgumentError, TypeError, ValueError):
            print('数据库连接格式无效，请检查 DATABASE_URL')
            return 1
    sys.path.insert(0, str(ROOT))
    from flask_shop import create_app, db, models
    from flask_shop.utils.schema_audit import schema_problems
    from flask_shop.utils.tenant_query import tenant_context

    app = create_app(cfg_name, initialize_schema=False, start_background=False)
    print("=" * 56)
    print("v1 go-live check")
    print("=" * 56)
    uri = app.config.get("SQLALCHEMY_DATABASE_URI") or ""
    print(f"config: {cfg_name}")
    print(f"db:     {database_summary(uri)}")
    print(f"mock:   ALLOW_MOCK_PAY={app.config.get('ALLOW_MOCK_PAY')}")
    print(f"sms:    SMS_DEV_MODE={app.config.get('SMS_DEV_MODE')}")

    fails = []
    warns = []

    if make_url(uri).get_backend_name() == 'sqlite':
        warns.append("当前为 SQLite；正式交付建议 MySQL")
    if cfg_name != 'product':
        warns.append('当前不是生产配置，不能作为正式上线验收')
    if app.config.get('PLATFORM_API_ENABLED'):
        warns.append('平台管理接口已启用；必须在网关限制管理网络并验证限流和密钥轮换')
    secret = app.config.get("SECRET_KEY") or ""
    if len(secret) < 32 or secret in getattr(
        __import__("config", fromlist=["Config"]).Config, "WEAK_SECRETS", set()
    ):
        fails.append("SECRET_KEY 过弱或过短")

    with app.app_context():
        try:
            schema_errors = schema_problems(db.engine, db.metadata)
        except Exception:
            print('BLOCKED: 无法只读检查数据库结构，请检查数据库连接和元数据读取权限')
            return 1
        if schema_errors:
            print('BLOCKED: 数据库结构与当前模型不匹配；请先备份并在隔离环境制定迁移方案：')
            for error in schema_errors:
                print('  -', error)
            return 1
        print('schema: 表、列及 MySQL 精确数值类型基础检查通过（不替代迁移验收）')
        with tenant_context(disabled=True):
            t = models.Tenant.query.filter_by(slug=tenant_slug).first()
            if not t:
                fails.append("指定店铺不存在，请核对 --tenant")
            else:
                print(f"tenant: {t.name} (id={t.id})")
                if t.status != 1:
                    fails.append('指定店铺已停用')
                if getattr(t, 'data_mode', None) == 'demo':
                    warns.append('指定店铺仍处于演示数据模式')
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
                staff = models.User.query.filter_by(tenant_id=t.id).all()
                if any(user.check_password("123456") for user in staff):
                    fails.append("本店员工存在默认密码 123456，请逐一检查并修改")

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
        print("PASS: 基础检查无阻断项，不能替代正式上线验收")
    elif not fails:
        print("PASS_WITH_WARNINGS: 基础检查有警告，不代表可以正式上线")
    else:
        print("BLOCKED: 请先处理 FAIL")
        return 1
    print("=" * 56)
    print("下一步人工项:")
    print("  1) 后台店铺设置上传微信/支付宝收款码")
    print("  2) 检查并修改所有员工弱密码（接口 POST /user/change-password/）")
    print("  3) 正式环境关 SMS_DEV_MODE，配置 HTTPS/域名")
    print("  4) 验证目标环境的备份恢复、支付短信和真实商家业务流程")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
