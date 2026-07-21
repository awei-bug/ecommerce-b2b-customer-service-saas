"""操作审计写入工具。"""
from flask import g, request

from flask_shop import db, models


def write_audit(action, resource_type=None, resource_id=None, detail=None, tenant_id=None,
                actor_type=None, actor_id=None):
    """
    写入审计日志。失败不抛到业务主流程（best-effort）。
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
            ip = request.headers.get('X-Forwarded-For', request.remote_addr)
            if ip and ',' in ip:
                ip = ip.split(',')[0].strip()
        except Exception:
            ip = None

        row = models.AuditLog(
            tenant_id=tid,
            actor_type=atype,
            actor_id=aid,
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id) if resource_id is not None else None,
            detail=(detail or '')[:512],
            ip=ip,
        )
        db.session.add(row)
        db.session.commit()
    except Exception as e:
        try:
            db.session.rollback()
        except Exception:
            pass
        print('audit write failed:', e)
