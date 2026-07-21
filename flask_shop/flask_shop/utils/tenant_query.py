"""
自动多租户隔离层（方案 2：根治）。

通过 SQLAlchemy 的 ``before_compile`` 事件，对所有 ``Model.query`` 与
``db.session.query(...)`` 在执行前自动注入 ``tenant_id`` 过滤，使**漏写**
``tenant_id`` 的查询也能被隔离，而不是上线后悄悄串数据。

设计要点
--------
1. 隔离依据：优先取显式 override（脚本 / 平台批量用 ``tenant_context``），
   否则取 ``flask.g.tenant_id``（请求内由鉴权中间件绑定）。
2. 豁免规则：模型没有 ``tenant_id`` 列（如 ``Tenant`` / ``Menu``）不做过滤。
3. 跨租户操作：平台中台、数据迁移、种子脚本用 ``tenant_context(disabled=True)``
   或环境变量 ``TENANT_FILTER_DISABLED=1`` 显式绕过。
4. 严格模式（可选）：环境变量 ``TENANT_STRICT=1`` 时，在请求上下文内查询带
   ``tenant_id`` 的模型却未绑定租户 -> 直接抛错，用于开发/CI 抓“忘绑租户”。

注意：INSERT/UPDATE/DELETE 同样会经过本事件；多租户语义下本就应限定租户，
平台批量操作请显式 disable。
"""
import os
import threading
from contextlib import contextmanager

from sqlalchemy import event, inspect
from sqlalchemy.exc import NoInspectionAvailable
from sqlalchemy.orm import Query

_local = threading.local()
_local.override_tenant_id = None  # None=未设置，使用 g.tenant_id
_local.disabled = False

_STRICT = os.environ.get('TENANT_STRICT', '0') == '1'
_installed = False


class TenantIsolationError(Exception):
    """严格模式下未绑定租户却查询租户数据。"""

    def __init__(self, message, status=500):
        super().__init__(message)
        self.message = message
        self.status = status


def current_tenant_id():
    """当前生效的租户 id：override 优先，其次 flask.g。"""
    override = getattr(_local, 'override_tenant_id', None)
    if override is not None:
        return override
    try:
        from flask import g
        return getattr(g, 'tenant_id', None)
    except RuntimeError:
        # 没有 Flask 应用/请求上下文（如脚本、迁移）
        return None


def tenant_filter_disabled():
    if getattr(_local, 'disabled', False):
        return True
    if os.environ.get('TENANT_FILTER_DISABLED') == '1':
        return True
    return False


@contextmanager
def tenant_context(tenant_id=None, disabled=False):
    """临时切换隔离上下文。

    用法::

        with tenant_context(tenant_id=target_id):
            rows = Product.query.all()          # 仅 target_id 租户

        with tenant_context(disabled=True):
            tenants = Tenant.query.all()        # 跨租户（平台/迁移）
    """
    prev_override = getattr(_local, 'override_tenant_id', None)
    prev_disabled = getattr(_local, 'disabled', False)
    if tenant_id is not None:
        _local.override_tenant_id = tenant_id
    if disabled:
        _local.disabled = True
    try:
        yield
    finally:
        _local.override_tenant_id = prev_override
        _local.disabled = prev_disabled


def with_tenant(tenant_id):
    """便捷：以指定租户身份执行查询。"""
    return tenant_context(tenant_id=tenant_id)


def disable_tenant_filter():
    _local.disabled = True


def enable_tenant_filter():
    _local.disabled = False


def _model_class_of(entity):
    if entity is None:
        return None
    try:
        mapper = inspect(entity)
    except (NoInspectionAvailable, TypeError):
        return None
    if mapper is None or not hasattr(mapper, 'columns'):
        return None
    return mapper


def _before_compile(query):
    # 已处理过则直接返回，避免 retval 递归重复注入
    if getattr(query, '_tenant_isolated', False):
        return query
    query._tenant_isolated = True

    if tenant_filter_disabled():
        return query

    tid = current_tenant_id()
    if tid is None:
        if _STRICT:
            for desc in query.column_descriptions:
                ent = desc.get('entity')
                mapper = _model_class_of(ent)
                if mapper is not None and 'tenant_id' in mapper.columns:
                    raise TenantIsolationError(
                        '查询涉及租户数据但未绑定租户上下文（TENANT_STRICT）', 500
                    )
        return query

    applied = set()
    for desc in query.column_descriptions:
        ent = desc.get('entity')
        mapper = _model_class_of(ent)
        if mapper is None or 'tenant_id' not in mapper.columns:
            continue
        cls = mapper.class_
        if cls in applied:
            continue
        # before_compile 触发时查询可能已含 LIMIT/OFFSET，临时关闭断言以追加 WHERE。
        # SQLAlchemy 2.0 最终编译顺序正确：WHERE 仍在 LIMIT 之前。
        try:
            query._enable_assertions = False
        except AttributeError:
            pass
        query = query.filter(cls.tenant_id == tid)
        applied.add(cls)
    query._tenant_isolated = True
    return query


def install_tenant_query():
    """注册 before_compile 事件（幂等）。在 db 创建后调用一次。"""
    global _installed
    if _installed:
        return
    event.listen(Query, 'before_compile', _before_compile, retval=True)
    _installed = True
