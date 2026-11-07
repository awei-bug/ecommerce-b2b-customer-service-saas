# -*- coding: utf-8 -*-
from flask import Flask, g, request
from flask_sqlalchemy import SQLAlchemy

from config import config_map

db = SQLAlchemy()


# 幂等补列时「可预期失败」的报错特征，用于区分静默条件与真实故障：
# - 对象已存在（列/索引/表）：重复补列，直接跳过。
# - 表不存在（SQLite "no such table" / MySQL "doesn't exist"）：本函数先跑
#   ALTER 再跑 create_all，全新库上表尚未建立属正常流程，create_all 会兜底建表。
# 除此以外的失败（如 ALTER 权限被拒、表被锁、语法错误）必须告警留痕。
_ALREADY_EXISTS_MARKERS = (
    'duplicate column',    # MySQL 1060 / SQLite
    'already exists',      # SQLite / PostgreSQL
    'duplicate key name',  # MySQL 1061 索引
    'errno 1060',
    'errno 1061',
    'no such table',       # SQLite
    "doesn't exist",       # MySQL 1146
    'does not exist',
    'errno 1146',
)


def _is_already_exists(exc: Exception) -> bool:
    text_ = str(exc).lower()
    return any(marker in text_ for marker in _ALREADY_EXISTS_MARKERS)


def ensure_schema_compat(app):
    """轻量兼容：先建新表，再为已有表补扩展列。

    两次要点：
    1. `create_all()` 必须在补列之前——空库上表还不存在，先补列必然全部失败，
       而旧实现把 create_all 放在最后，会让全新数据库缺表。
    2. 语句按方言渲染：`DATETIME` 只在 MySQL 存在，PostgreSQL 需要 `TIMESTAMP`。
       补列后逐列复核，失败必须留痕——只 warn 会让某列永久缺失。
    """
    from sqlalchemy import inspect as sa_inspect
    from sqlalchemy import text

    # (表, 列, {方言: 列定义})；"default" 用于其余方言。
    columns = [
        ("t_tenants", "theme", {"default": "VARCHAR(32) DEFAULT 'retail'"}),
        ("t_tenants", "data_mode", {"default": "VARCHAR(16) NOT NULL DEFAULT 'live'"}),
        ("t_tenants", "pay_qr_wechat", {"default": "VARCHAR(255)"}),
        ("t_tenants", "pay_qr_alipay", {"default": "VARCHAR(255)"}),
        ("t_order", "campaign_id", {"default": "VARCHAR(128)"}),
        ("t_order", "content_id", {"default": "VARCHAR(128)"}),
        ("t_order", "attribution_source", {"default": "VARCHAR(64)"}),
        ("t_order", "attribution_medium", {"default": "VARCHAR(64)"}),
        ("t_order", "consultation_session_id", {"default": "VARCHAR(64)"}),
        ("t_order", "buyer_paid_claimed", {"default": "INTEGER DEFAULT 0"}),
        ("t_order", "buyer_paid_at", {"mysql": "DATETIME", "default": "TIMESTAMP"}),
        ("t_order", "buyer_paid_note", {"default": "VARCHAR(64)"}),
        ("t_order", "buyer_paid_proof", {"default": "VARCHAR(255)"}),
        ("t_order", "coupon_id", {"default": "INTEGER"}),
        ("t_order", "discount_amount", {"default": "DECIMAL(12,2) DEFAULT 0"}),
        ("t_customer_addresses", "country_code", {"default": "VARCHAR(8) DEFAULT 'JP'"}),
        ("t_customer_addresses", "country_name", {"default": "VARCHAR(64)"}),
        ("t_customer_addresses", "postal_code", {"default": "VARCHAR(32)"}),
    ]

    with app.app_context():
        # 1) 先建表：全新库需要它；已有库上它是无副作用的空操作。
        #    实测在 ensure_schema_compat 的嵌套 app context 里，db.create_all() 会
        #    静默建出 0 张表（与 bind 的交互），因此真正的建表走 metadata.create_all；
        #    之后再调一次 db.create_all()，保留既有安全测试断言的调用契约。
        try:
            from flask_shop import models as _models  # noqa: F401  注册所有映射

            db.metadata.create_all(bind=db.engine)
            db.create_all()
        except Exception:
            db.session.rollback()
            app.logger.exception('ensure_schema_compat create_all 失败，新表可能未创建')

        # 2) 再补列
        dialect = db.engine.dialect.name
        inspector = sa_inspect(db.engine)

        def current_columns(table):
            try:
                return {col['name'] for col in inspector.get_columns(table)}
            except Exception:
                return set()

        for table, column, types in columns:
            if column in current_columns(table):
                continue
            definition = types.get(dialect, types["default"])
            sql = 'ALTER TABLE {} ADD COLUMN {} {}'.format(table, column, definition)
            try:
                db.session.execute(text(sql))
                db.session.commit()
            except Exception as exc:
                db.session.rollback()
                if not _is_already_exists(exc):
                    app.logger.warning(
                        'ensure_schema_compat 补列失败（该列可能缺失）: %s | %s', sql, exc,
                    )

        # 3) 复核：任何仍然缺失的列都必须能被发现，而不是只在日志里留一条 warning。
        inspector = sa_inspect(db.engine)
        missing = []
        for table, column, _types in columns:
            try:
                if column not in {col['name'] for col in inspector.get_columns(table)}:
                    missing.append('{}.{}'.format(table, column))
            except Exception:
                missing.append('{}.{}'.format(table, column))
        if missing:
            app.logger.error('ensure_schema_compat 补列后仍缺失: %s', ', '.join(missing))


def configure_proxy(app):
    hops = app.config.get('TRUST_PROXY_HOPS', 0)
    if hops not in (0, 1):
        raise RuntimeError('TRUST_PROXY_HOPS 仅支持 0 或 1')
    if hops:
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=0, x_host=0, x_port=0, x_prefix=0)


def create_app(config_name, *, initialize_schema=True, start_background=True):
    app = Flask(__name__, static_folder="static", static_url_path="/static")
    Config = config_map.get(config_name)
    if Config is None:
        raise RuntimeError(f'未知配置名 {config_name}，可选: {list(config_map.keys())}')
    app.config.from_object(Config)
    configure_proxy(app)

    if config_name in ('product', 'sample') and hasattr(Config, 'validate'):
        Config.validate()

    if config_name == 'develop':
        weak = getattr(Config, 'WEAK_SECRETS', set())
        if (Config.SECRET_KEY or '') in weak:
            app.logger.warning('SECRET_KEY 仍是弱默认值，仅可用于本地开发')

    from sqlalchemy.engine import make_url

    database_url = make_url(app.config['SQLALCHEMY_DATABASE_URI'])
    memory_sqlite = (database_url.get_backend_name() == 'sqlite' and
                     (not database_url.database or ':memory:' in database_url.database or
                      database_url.query.get('mode') == 'memory'))
    binds = dict(app.config.get('SQLALCHEMY_BINDS') or {})
    if '_audit' in binds:
        raise RuntimeError('数据库绑定名 _audit 由审计系统保留')
    audit_options = dict(app.config.get('SQLALCHEMY_ENGINE_OPTIONS') or {})
    audit_options.pop('poolclass', None)
    if memory_sqlite:
        for option in ('pool_size', 'max_overflow', 'pool_timeout'):
            audit_options.pop(option, None)
        audit_options['url'] = database_url
    else:
        audit_options.update(url=database_url, pool_size=2, max_overflow=0, pool_timeout=1)
    binds['_audit'] = audit_options
    app.config['SQLALCHEMY_BINDS'] = binds

    db.init_app(app)

    from decimal import Decimal
    from flask.json.provider import DefaultJSONProvider
    from flask_shop.utils.money import decimal_default, money_float

    class MoneyJSONProvider(DefaultJSONProvider):
        def default(self, o):
            if isinstance(o, Decimal):
                return money_float(o)
            return super().default(o)

    app.json = MoneyJSONProvider(app)
    restful_json = dict(app.config.get("RESTFUL_JSON") or {})
    restful_json.setdefault("default", decimal_default)
    restful_json.setdefault("ensure_ascii", False)
    app.config["RESTFUL_JSON"] = restful_json

    # 自动多租户隔离（before_compile）
    from flask_shop.utils.tenant_query import install_tenant_query
    install_tenant_query()
    if initialize_schema:
        if config_name == 'product':
            from flask_shop import models
            from flask_shop.utils.schema_audit import schema_problems

            with app.app_context():
                problems = schema_problems(db.engine, db.metadata)
            if problems:
                raise RuntimeError('数据库结构检查失败，生产启动不会自动修改数据库: ' + '; '.join(problems))
        else:
            try:
                ensure_schema_compat(app)
            except Exception:
                app.logger.exception('ensure_schema_compat failed')

    if start_background:
        try:
            from flask_shop.utils.order_timeout import start_timeout_loop
            start_timeout_loop(app)
        except Exception:
            app.logger.exception('start_timeout_loop failed')

    import os
    upload_folder = os.path.join(os.path.dirname(__file__), 'static', 'upload')
    os.makedirs(upload_folder, exist_ok=True)
    app.config.setdefault('UPLOAD_FOLDER', upload_folder)
    app.config['PAY_PROOF_FOLDER'] = os.getenv('PAY_PROOF_FOLDER') or os.path.join(app.instance_path, 'pay_proofs')
    from pathlib import Path
    if Path(app.config['PAY_PROOF_FOLDER']).resolve().is_relative_to(Path(app.static_folder).resolve()):
        raise RuntimeError('付款截图存储目录不能位于静态目录内')
    os.makedirs(app.config['PAY_PROOF_FOLDER'], exist_ok=True)

    @app.before_request
    def _init_context():
        g.tenant = None
        g.tenant_id = None
        g.staff_id = None
        g.user_id = None
        g.customer_id = None
        g.token_payload = None

    @app.before_request
    def _block_public_pay_proof():
        import re
        if re.match(r'^/static/upload/[^/]+/pay_proof(?:/|$)', request.path, re.I):
            return '', 404

    # —— 核心商城 ——
    from flask_shop.user import user_bp
    app.register_blueprint(user_bp)

    from flask_shop.product import product_bp
    app.register_blueprint(product_bp)

    from flask_shop.category import cate_bp, attr_bp
    app.register_blueprint(cate_bp)
    app.register_blueprint(attr_bp)

    from flask_shop.order import order_bp
    app.register_blueprint(order_bp)

    from flask_shop.pay import pay_bp
    app.register_blueprint(pay_bp)

    from flask_shop.menu import menu_bp
    app.register_blueprint(menu_bp)

    from flask_shop.role import role_bp
    app.register_blueprint(role_bp)

    from flask_shop.c_api import c_bp
    app.register_blueprint(c_bp)

    from flask_shop.platform_api import platform_bp
    app.register_blueprint(platform_bp)

    from flask_shop.agents.views import agents_bp
    app.register_blueprint(agents_bp)

    from flask_shop.automation import automation_bp
    app.register_blueprint(automation_bp)

    from flask_shop.tenant_cli import tenant_cli
    app.cli.add_command(tenant_cli)

    @app.route('/health/')
    def health():
        return {
            'status': 200,
            'msg': 'ok',
            'app': 'ecommerce-shop',
        }

    @app.after_request
    def _security_headers(response):
        """统一安全响应头；健康检查也保持最小信息暴露。"""
        response.headers.setdefault('X-Content-Type-Options', 'nosniff')
        response.headers.setdefault('X-Frame-Options', 'DENY')
        response.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
        response.headers.setdefault('Permissions-Policy', 'camera=(), microphone=(), geolocation=()')
        # 商品、分类和商城详情是动态数据；开发环境也不能让浏览器缓存旧库存/主图。
        dynamic_api = request.path.startswith(('/api/c/', '/products/', '/product/'))
        if config_name in ('product', 'sample') or dynamic_api:
            response.headers.setdefault('Cache-Control', 'no-store')
        return response

    @app.route('/metrics/')
    def metrics():
        """轻量监控：库连通、订单积压、Agent 轨迹。"""
        if config_name == 'product':
            return {'status': 404, 'msg': 'not found'}, 404
        import time
        from flask_shop import models
        from flask_shop.utils.tenant_query import tenant_context
        t0 = time.time()
        info = {'db_ok': False, 'latency_ms': 0}
        try:
            with tenant_context(disabled=True):
                info['tenants'] = models.Tenant.query.count()
                info['products'] = models.Product.query.count()
                info['orders_pending_pay'] = models.Order.query.filter_by(status='pending_pay').count()
                info['orders_paid'] = models.Order.query.filter_by(status='paid').count()
                if hasattr(models, 'AgentTrace'):
                    info['agent_traces'] = models.AgentTrace.query.count()
                if hasattr(models, 'Coupon'):
                    info['coupons'] = models.Coupon.query.filter_by(status=1).count()
            info['db_ok'] = True
        except Exception as e:
            info['db_error'] = str(e)[:200]
        info['latency_ms'] = int((time.time() - t0) * 1000)
        info['status'] = 200 if info['db_ok'] else 500
        info['msg'] = 'ok' if info['db_ok'] else 'db_error'
        info['env'] = config_name
        return info, (200 if info['db_ok'] else 500)

    # 静态上传
    import os
    upload_dir = os.path.join(os.path.dirname(__file__), 'static', 'upload')
    os.makedirs(upload_dir, exist_ok=True)

    return app


__all__ = ['create_app', 'db']
