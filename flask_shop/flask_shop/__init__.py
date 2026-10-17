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
    """轻量兼容：为已有库补租户扩展列（忽略已存在错误）。"""
    from sqlalchemy import text
    alters = [
        "ALTER TABLE t_tenants ADD COLUMN theme VARCHAR(32) DEFAULT 'retail'",
        "ALTER TABLE t_tenants ADD COLUMN data_mode VARCHAR(16) NOT NULL DEFAULT 'live'",
        "ALTER TABLE t_tenants ADD COLUMN pay_qr_wechat VARCHAR(255)",
        "ALTER TABLE t_tenants ADD COLUMN pay_qr_alipay VARCHAR(255)",
        "ALTER TABLE t_order ADD COLUMN campaign_id VARCHAR(128)",
        "ALTER TABLE t_order ADD COLUMN content_id VARCHAR(128)",
        "ALTER TABLE t_order ADD COLUMN attribution_source VARCHAR(64)",
        "ALTER TABLE t_order ADD COLUMN attribution_medium VARCHAR(64)",
        "ALTER TABLE t_order ADD COLUMN consultation_session_id VARCHAR(64)",
        "ALTER TABLE t_order ADD COLUMN buyer_paid_claimed INTEGER DEFAULT 0",
        "ALTER TABLE t_order ADD COLUMN buyer_paid_at DATETIME",
        "ALTER TABLE t_order ADD COLUMN buyer_paid_note VARCHAR(64)",
        "ALTER TABLE t_order ADD COLUMN buyer_paid_proof VARCHAR(255)",
        "ALTER TABLE t_order ADD COLUMN coupon_id INTEGER",
        "ALTER TABLE t_order ADD COLUMN discount_amount DECIMAL(12,2) DEFAULT 0",
        "ALTER TABLE t_product MODIFY COLUMN price DECIMAL(12,2)",
        "ALTER TABLE t_order MODIFY COLUMN price DECIMAL(12,2)",
        "ALTER TABLE t_order MODIFY COLUMN goods_amount DECIMAL(12,2)",
        "ALTER TABLE t_order MODIFY COLUMN freight_amount DECIMAL(12,2)",
        "ALTER TABLE t_order_detail MODIFY COLUMN price DECIMAL(12,2)",
        "ALTER TABLE t_order_detail MODIFY COLUMN total_price DECIMAL(12,2)",
        "ALTER TABLE t_payments MODIFY COLUMN amount DECIMAL(12,2)",
        "ALTER TABLE t_coupons MODIFY COLUMN threshold DECIMAL(12,2)",
        "ALTER TABLE t_coupons MODIFY COLUMN amount_off DECIMAL(12,2)",
        "ALTER TABLE t_freight_templates MODIFY COLUMN fixed_fee DECIMAL(12,2)",
        "ALTER TABLE t_freight_templates MODIFY COLUMN per_piece_fee DECIMAL(12,2)",
        "ALTER TABLE t_freight_templates MODIFY COLUMN free_amount DECIMAL(12,2)",
        "ALTER TABLE t_customer_addresses ADD COLUMN country_code VARCHAR(8) DEFAULT 'JP'",
        "ALTER TABLE t_customer_addresses ADD COLUMN country_name VARCHAR(64)",
        "ALTER TABLE t_customer_addresses ADD COLUMN postal_code VARCHAR(32)",
    ]
        # agent traces table created via db.create_all on develop; product uses migrate

    with app.app_context():
        for sql in alters:
            try:
                db.session.execute(text(sql))
                db.session.commit()
            except Exception as exc:
                db.session.rollback()
                # 「列/索引已存在」是幂等补列的预期结果，可以静默；
                # 其余失败必须留痕：否则这一列没补上，应用仍能正常启动，
                # 直到线上真正读到该列才以 unknown column 崩掉，很难定位。
                if not _is_already_exists(exc):
                    app.logger.warning(
                        'ensure_schema_compat 补列失败（该列可能缺失）: %s | %s', sql, exc,
                    )
        try:
            # 新表：多智能体轨迹
            from flask_shop import models as _m
            db.create_all()
        except Exception:
            db.session.rollback()
            app.logger.exception('ensure_schema_compat create_all 失败，新表可能未创建')




def create_app(config_name):
    app = Flask(__name__, static_folder="static", static_url_path="/static")
    Config = config_map.get(config_name)
    if Config is None:
        raise RuntimeError(f'未知配置名 {config_name}，可选: {list(config_map.keys())}')
    app.config.from_object(Config)

    if config_name in ('product', 'sample') and hasattr(Config, 'validate'):
        Config.validate()

    if config_name == 'develop':
        weak = getattr(Config, 'WEAK_SECRETS', set())
        if (Config.SECRET_KEY or '') in weak:
            app.logger.warning('SECRET_KEY 仍是弱默认值，仅可用于本地开发')

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
    try:
        ensure_schema_compat(app)
    except Exception:
        app.logger.exception('ensure_schema_compat failed')

    try:
        from flask_shop.utils.order_timeout import start_timeout_loop
        start_timeout_loop(app)
    except Exception:
        app.logger.exception('start_timeout_loop failed')

    import os
    upload_folder = os.path.join(os.path.dirname(__file__), 'static', 'upload')
    os.makedirs(upload_folder, exist_ok=True)
    app.config.setdefault('UPLOAD_FOLDER', upload_folder)

    @app.before_request
    def _init_context():
        g.tenant = None
        g.tenant_id = None
        g.staff_id = None
        g.user_id = None
        g.customer_id = None
        g.token_payload = None

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
