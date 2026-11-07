"""跨系统领域事件端点。

独立蓝图，避免把内网接口挂进商城业务蓝图的鉴权链。
"""
from flask import Blueprint

events_bp = Blueprint('events', __name__, url_prefix='/api')

from . import views  # noqa: E402,F401  注册路由，须在 events_bp 定义之后
