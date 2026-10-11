"""操作审计写入工具。"""
from flask import g, request

from flask_shop import db, models


def write_audit(action, resource_type=None, resource_id=None, detail=None, tenant_id=None,
                actor_type=None, actor_id=None):
    """
    写入审计日志。失败不抛到业务主流程（best-effort）。

    实现要点：
    - 优先用 SAVEPOINT，避免审计失败 rollback 掉尚未 commit 的业务改动
    - 若处于无外层事务场景，则独立 commit
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
        if ip:
            ip = str(ip)[:64]

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

        # 有活跃事务时用嵌套保存点，避免失败污染外层
        try:
            in_tx = db.session().in_transaction() if callable(getattr(db, 'session', None)) else db.session.in_transaction()
        except Exception:
            try:
                in_tx = bool(db.session.dirty or db.session.new or db.session.deleted)
            except Exception:
                in_tx = False

        # Flask-SQLAlchemy: session.in_transaction() available on Session
        try:
            sess = db.session
            if hasattr(sess, 'in_transaction') and sess.in_transaction():
                with sess.begin_nested():
                    sess.add(row)
            else:
                sess.add(row)
                sess.commit()
        except Exception:
            # 回退：尽力写入
            db.session.add(row)
            db.session.commit()
    except Exception as e:
        try:
            db.session.rollback()
        except Exception:
            pass
        print('audit write failed:', e)
