from flask import Flask
from flask_cors import CORS
import os

from flask_shop import create_app, db


def _resolve_config_name():
    name = (os.getenv('FLASK_CONFIG') or '').strip().lower()
    if name in ('develop', 'product', 'test'):
        return name
    env = (os.getenv('FLASK_ENV') or os.getenv('ENV') or 'develop').strip().lower()
    if env in ('production', 'product', 'prod'):
        return 'product'
    if env in ('testing', 'test'):
        return 'test'
    return 'develop'


config_name = _resolve_config_name()
app = create_app(config_name)

cors_origins = app.config.get('CORS_ORIGINS') or []
if config_name == 'product':
    CORS(
        app,
        origins=cors_origins,
        supports_credentials=True,
        allow_headers=['Content-Type', 'Authorization', 'token', 'X-Tenant-Slug', 'X-Tenant-Id', 'X-Customer-Token'],
        methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS', 'PATCH'],
    )
else:
    origins = list(cors_origins) or [
        'http://localhost:8080', 'http://127.0.0.1:8080',
        'http://localhost:8081', 'http://127.0.0.1:8081',
        'http://localhost:5173', 'http://127.0.0.1:5173',
    ]
    # 本地多端口联调：云购 API 是唯一登录签发点，其它端口要靠 cookie 调
    # /user/session/。这些源只并入非生产配置；生产必须显式配置 CORS_ORIGINS。
    for extra in (
        'http://localhost:8090', 'http://127.0.0.1:8090',
        'http://localhost:5174', 'http://127.0.0.1:5174',
        'http://localhost:5175', 'http://127.0.0.1:5175',
    ):
        if extra not in origins:
            origins.append(extra)
    CORS(
        app,
        origins=origins,
        supports_credentials=True,
        allow_headers=['Content-Type', 'Authorization', 'token', 'X-Tenant-Slug', 'X-Tenant-Id', 'X-Customer-Token'],
        methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS', 'PATCH'],
    )

@app.cli.command('close-expired-orders')
def close_expired_orders_cmd():
    """关闭超时未支付订单并回滚库存。建议 cron 每 5～10 分钟执行。"""
    from flask_shop.utils.order_timeout import close_expired_pending_orders
    from flask_shop.utils.tenant_query import tenant_context

    with tenant_context(disabled=True):
        n = close_expired_pending_orders()
    print(f'closed={n}')


if __name__ == '__main__':
    host = os.getenv('FLASK_HOST', '0.0.0.0')
    port = int(os.getenv('FLASK_PORT', '5000'))
    debug = bool(app.config.get('DEBUG'))
    app.run(host=host, port=port, debug=debug)
