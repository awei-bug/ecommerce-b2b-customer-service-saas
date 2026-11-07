"""操作审计写入工具。"""
from flask import current_app, g, request
from sqlalchemy import insert
from sqlalchemy.pool import SingletonThreadPool, StaticPool

from flask_shop import db, models


def write_audit(action, resource_type=None, resource_id=None, detail=None, tenant_id=None,
                actor_type=None, actor_id=None):
    """
    写入审计日志。失败不抛到业务主流程（best-effort）。

    审计使用独立数据库事务，不提交或回滚调用方会话。
    调用方应在业务提交后调用，审计失败不影响业务结果。
    """
    try:
        tid = tenant_id if tenant_id is not None else getattr(g, 'tenant_id', None)
        atype = actor_type
        aid = actor_id
        if atype is None:
            if getattr(g, 'staff_id', None):
                atype = 'staff'
                aid = g.staff_id
            elif getattr(g, 'customer_id', None):
                atype = 'customer'
                aid = g.customer_id
            else:
                atype = 'system'
                aid = None
        ip = None
        try:
            ip = request.remote_addr
        except Exception:
            ip = None
        if ip:
            ip = str(ip)[:64]

        values = dict(
            tenant_id=tid,
            actor_type=atype,
            actor_id=aid,
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id) if resource_id is not None else None,
            detail=(detail or '')[:512],
            ip=ip,
        )

        engine = db.engines.get('_audit', db.engine)
        if isinstance(engine.pool, (StaticPool, SingletonThreadPool)):
            raise RuntimeError('cannot isolate audit transaction with a single-connection pool')
        with engine.begin() as connection:
            connection.execute(insert(models.AuditLog).values(**values))
        return True
    except Exception as e:
        current_app.logger.error('audit write failed action=%s error_type=%s', action, type(e).__name__)
        return False
