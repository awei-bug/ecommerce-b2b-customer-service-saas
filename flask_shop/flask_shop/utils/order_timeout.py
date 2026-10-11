"""待支付订单超时关闭 + 回滚库存。"""
from datetime import datetime, timedelta

from flask import current_app

from flask_shop import db, models
from flask_shop.utils.order_state import CLOSED, PENDING_PAY, transit_order
from flask_shop.utils.stock import inc_stock
from flask_shop.utils.audit import write_audit


def close_expired_pending_orders(tenant_id=None, limit=200):
    """
    关闭超时未支付订单并回库存。
    返回关闭数量。可被定时任务或列表接口懒触发。
    """
    minutes = int(current_app.config.get('ORDER_PENDING_TIMEOUT_MINUTES') or 0)
    if minutes <= 0:
        return 0

    deadline = datetime.now() - timedelta(minutes=minutes)
    q = models.Order.query.filter(
        models.Order.status == PENDING_PAY,
        models.Order.create_time < deadline,
        db.or_(
            models.Order.buyer_paid_claimed.is_(None),
            models.Order.buyer_paid_claimed == 0,
        ),
    )
    if tenant_id is not None:
        q = q.filter(models.Order.tenant_id == tenant_id)
    orders = q.order_by(models.Order.id.asc()).limit(limit).all()
    closed = 0
    for order in orders:
        try:
            transit_order(order, CLOSED, reason=f'超时未支付自动关闭({minutes}分钟)')
            for d in order.order_detail or []:
                if d.pid and d.number:
                    inc_stock(order.tenant_id, d.pid, d.number, sku_id=getattr(d, 'sku_id', None))
            # 先提交业务，再 best-effort 审计，避免审计失败回滚关单
            db.session.commit()
            write_audit(
                'order.auto_close',
                'order',
                order.id,
                f'timeout={minutes}m',
                tenant_id=order.tenant_id,
                actor_type='system',
            )
            closed += 1
        except Exception:
            db.session.rollback()
            continue
    return closed


def start_timeout_loop(app, interval_seconds=300):
    """进程内定时关单。测试环境 / 超时关闭时不启动。"""
    import os
    import threading
    import time

    if app.config.get("TESTING"):
        return
    if int(app.config.get("ORDER_PENDING_TIMEOUT_MINUTES") or 0) <= 0:
        return
    if getattr(app, "_timeout_loop_started", False):
        return
    # Flask debug reloader 的父进程不要再开一条线程
    if os.environ.get("WERKZEUG_RUN_MAIN") == "false":
        return
    app._timeout_loop_started = True

    def loop():
        from flask_shop.utils.tenant_query import tenant_context
        while True:
            time.sleep(max(30, int(interval_seconds)))
            try:
                with app.app_context():
                    with tenant_context(disabled=True):
                        n = close_expired_pending_orders()
                        if n:
                            app.logger.info("auto-closed expired orders: %s", n)
            except Exception:
                try:
                    app.logger.exception("order timeout loop failed")
                except Exception:
                    pass

    threading.Thread(target=loop, name="order-timeout", daemon=True).start()
