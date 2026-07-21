"""
多租户上下文工具。

解析顺序（登录前）：
1. 请求头 X-Tenant-Id
2. 请求头 X-Tenant-Slug
3. JSON/表单字段 tenant_id / tenant_slug
4. 查询参数 tenant_id / tenant_slug

登录后以 JWT 中的 tenant_id 为准；若请求头也带了租户，必须与 JWT 一致。
"""
from functools import wraps

from flask import g, request


class TenantError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.message = message
        self.status = status


def _parse_int(value):
    if value is None or value == '':
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def resolve_tenant_identifiers():
    """从请求中解析租户标识，不查库。"""
    tenant_id = _parse_int(request.headers.get('X-Tenant-Id'))
    tenant_slug = request.headers.get('X-Tenant-Slug')

    if tenant_id is None and request.is_json and request.get_json(silent=True):
        body = request.get_json(silent=True) or {}
        tenant_id = _parse_int(body.get('tenant_id'))
        tenant_slug = tenant_slug or body.get('tenant_slug')

    if tenant_id is None:
        tenant_id = _parse_int(request.args.get('tenant_id'))
    if not tenant_slug:
        tenant_slug = request.args.get('tenant_slug')
    if not tenant_slug and request.form:
        tenant_slug = request.form.get('tenant_slug')
        if tenant_id is None:
            tenant_id = _parse_int(request.form.get('tenant_id'))

    return tenant_id, (tenant_slug.strip() if isinstance(tenant_slug, str) and tenant_slug.strip() else None)


def load_tenant(tenant_id=None, tenant_slug=None):
    """按 id 或 slug 加载租户；停用租户视为不存在。"""
    from flask_shop import models

    query = models.Tenant.query.filter(models.Tenant.status == 1)
    tenant = None
    if tenant_id is not None:
        tenant = query.filter(models.Tenant.id == tenant_id).first()
    elif tenant_slug:
        tenant = query.filter(models.Tenant.slug == tenant_slug).first()
    return tenant


def bind_tenant(tenant):
    """写入 flask.g"""
    g.tenant = tenant
    g.tenant_id = tenant.id if tenant else None


def get_tenant_id():
    return getattr(g, 'tenant_id', None)


def require_tenant_id():
    tid = get_tenant_id()
    if not tid:
        raise TenantError('缺少租户上下文，请登录或传递 X-Tenant-Slug / X-Tenant-Id', 401)
    return tid


def tenant_filter(model):
    """返回当前租户下的基础 query。"""
    tid = require_tenant_id()
    return model.query.filter(model.tenant_id == tid)


def get_for_tenant(model, obj_id):
    """按主键 + 当前租户取对象，跨租户返回 None。"""
    tid = require_tenant_id()
    return model.query.filter(model.id == obj_id, model.tenant_id == tid).first()


def ensure_same_tenant(obj):
    """对象不属于当前租户则返回 False。"""
    if obj is None:
        return False
    tid = get_tenant_id()
    return getattr(obj, 'tenant_id', None) == tid


def tenant_required(view_func):
    """要求请求已绑定租户（登录接口用 slug/id 解析后可使用）。"""
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        try:
            require_tenant_id()
        except TenantError as e:
            return {'status': e.status, 'msg': e.message}
        return view_func(*args, **kwargs)
    return wrapper
