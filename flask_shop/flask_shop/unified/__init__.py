"""统一经营视图聚合端点。

宿主后台只发一个同源请求，由服务端向三个上游取数。这样前端不必处理
跨域、不必持有内网令牌，单个上游故障也不会让整个看板白屏。
"""
from flask import Blueprint

unified_bp = Blueprint('unified', __name__, url_prefix='/api/unified')

from . import views  # noqa: E402,F401  注册路由，须在 unified_bp 定义之后
