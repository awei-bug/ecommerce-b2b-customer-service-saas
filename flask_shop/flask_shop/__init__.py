from flask import Flask, g
from flask_sqlalchemy import SQLAlchemy

from config import config_map

db = SQLAlchemy()

# 注册自动多租户隔离（before_compile 注入 tenant_id 过滤）
from flask_shop.utils.tenant_query import install_tenant_query  # noqa: E402

install_tenant_query()


def create_app(config_name):
    app = Flask(__name__)
    Config = config_map.get(config_name)
    if Config is None:
        raise RuntimeError(f'未知配置名: {config_name}，可选: {list(config_map.keys())}')
    app.config.from_object(Config)

    # 生产配置强制校验（弱 SECRET_KEY 直接拒绝启动）
    if config_name == 'product' and hasattr(Config, 'validate'):
        Config.validate()

    db.init_app(app)

    # 每个请求初始化租户相关 g 字段
    @app.before_request
    def _init_tenant_context():
        g.tenant = None
        g.tenant_id = None
        g.staff_id = None
        g.user_id = None
        g.token_payload = None

    from flask_shop.user import user_bp
    app.register_blueprint(user_bp)

    from flask_shop.menu import menu_bp
    app.register_blueprint(menu_bp)

    from flask_shop.role import role_bp
    app.register_blueprint(role_bp)

    from flask_shop.category import cate_bp
    app.register_blueprint(cate_bp)

    from flask_shop.category import attr_bp
    app.register_blueprint(attr_bp)

    from flask_shop.product import product_bp
    app.register_blueprint(product_bp)

    from flask_shop.order import order_bp
    app.register_blueprint(order_bp)

    from flask_shop.shipment import shipment_bp
    app.register_blueprint(shipment_bp)

    from flask_shop.logistics import logistics_bp
    app.register_blueprint(logistics_bp)

    from flask_shop.pay import pay_bp
    app.register_blueprint(pay_bp)

    from flask_shop.c_api import c_bp
    app.register_blueprint(c_bp)

    from flask_shop.platform_api import platform_bp
    app.register_blueprint(platform_bp)

    # 健康检查：便于部署探活
    @app.route('/health/')
    def health():
        return {'status': 200, 'msg': 'ok'}

    return app
