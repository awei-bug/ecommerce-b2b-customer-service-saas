from flask import Blueprint
from flask_restful import Api

# C 端公开/半公开接口（阶段 1.5 骨架）
# 租户通过 X-Tenant-Slug 或 query tenant_slug 指定
c_bp = Blueprint('c', __name__, url_prefix='/api/c')
c_api = Api(c_bp)

from . import views  # noqa: E402,F401
