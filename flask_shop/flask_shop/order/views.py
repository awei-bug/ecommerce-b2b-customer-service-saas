import csv
import io
import uuid
from datetime import datetime

from flask import Response, request, current_app, g
from flask_restful import Resource, reqparse

from flask_shop import models, db
from flask_shop.order import order_api, order_bp
from flask_shop.utils.token import login_required
from flask_shop.utils.rbac import login_and_permission
from flask_shop.utils.tenant import get_for_tenant, require_tenant_id, tenant_filter
from flask_shop.utils.order_state import (
    CLOSED,
    COMPLETED,
    OrderStateError,
    PENDING_PAY,
    REFUNDED,
    REFUNDING,
    SHIPPED,
    transit_order,
)
from flask_shop.utils.stock import StockError, dec_stock, inc_stock
from flask_shop.utils.audit import write_audit
from flask_shop.utils.freight import calc_order_freight
from flask_shop.utils.money import money_add, money_float, money_mul


def _gen_order_no(tenant_id):
    ts = datetime.now().strftime('%Y%m%d%H%M%S')
    return f'O{tenant_id}{ts}{uuid.uuid4().hex[:6].upper()}'


def _filter_orders_query(args):
    query = tenant_filter(models.Order)
    if args.get('name'):
        query = query.filter(models.Order.address.like(f"%{args['name']}%"))
    if args.get('status'):
        query = query.filter(models.Order.status == args['status'])
    if args.get('order_no'):
        query = query.filter(models.Order.order_no == args['order_no'])
    claimed = args.get('claimed')
    if claimed in (1, '1', True, 'true', 'True'):
        query = query.filter(models.Order.buyer_paid_claimed == 1)
    return query.order_by(
        models.Order.buyer_paid_claimed.desc(),
        models.Order.id.desc(),
    )


class Orders(Resource):
    # get 需 order:read；post 在方法内再校验 order:create
    method_decorators = [login_required]

    def get(self):
        from flask_shop.utils.rbac import staff_has_permission
        if not staff_has_permission('order:read'):
            return {'status': 403, 'msg': '无权限查看订单'}
        # 懒触发：读取订单列表前，关闭本租户超时未支付订单并回收库存。
        # ORDER_PENDING_TIMEOUT_MINUTES<=0 时函数为 no-op，不影响性能。
        try:
            from flask_shop.utils.order_timeout import close_expired_pending_orders
            close_expired_pending_orders(tenant_id=require_tenant_id())
        except Exception:
            current_app.logger.exception('auto-close expired orders failed')
        parser = reqparse.RequestParser()
        parser.add_argument('name', type=str, location='args')
        parser.add_argument('status', type=str, location='args')
        parser.add_argument('order_no', type=str, location='args')
        parser.add_argument('claimed', type=int, location='args')
        parser.add_argument('pageNum', type=int, location='args', default=1)
        parser.add_argument('pageSize', type=int, location='args', default=20)
        args = parser.parse_args()
        query = _filter_orders_query(args)
        page = max(int(args.get('pageNum') or 1), 1)
        size = min(max(int(args.get('pageSize') or 20), 1), 100)
        total = query.count()
        order_list = query.offset((page - 1) * size).limit(size).all()
        return {
            'status': 200,
            'msg': '获取订单列表成功',
            'data': [order.to_dict() for order in order_list],
            'total': total,
            'pageNum': page,
            'pageSize': size,
        }

    def post(self):
        # 写操作单独校验
        from flask_shop.utils.rbac import staff_has_permission
        if not staff_has_permission('order:create'):
            return {'status': 403, 'msg': '无权限创建订单'}
        body = request.get_json(silent=True) or {}
        items = body.get('items') or []
        address = body.get('address') or ''
        if not items:
            return {'status': 400, 'msg': 'items 不能为空'}

        tenant_id = require_tenant_id()
        total_price = 0.0
        total_number = 0
        line_rows = []

        for it in items:
            pid = it.get('pid')
            number = int(it.get('number') or 0)
            sku_id = it.get('sku_id')
            if not pid or number <= 0:
                return {'status': 400, 'msg': '商品或数量不合法'}
            product = get_for_tenant(models.Product, pid)
            if not product:
                return {'status': 404, 'msg': f'商品 {pid} 不存在'}
            # B 端代客下单：禁止下架商品（state=0）；state 为 None 或 2 视为可售
            st = getattr(product, 'state', None)
            if st is not None and int(st) == 0:
                return {'status': 400, 'msg': f'商品 {product.name} 已下架，不可下单'}
            unit_price = money_float(product.price)
            sku_label = None
            if sku_id:
                sku = models.ProductSku.query.filter_by(
                    id=sku_id, tenant_id=tenant_id, product_id=pid, status=1
                ).first()
                if not sku:
                    return {'status': 400, 'msg': f'SKU {sku_id} 不存在'}
                unit_price = money_float(sku.price if sku.price is not None else product.price)
                sku_label = sku.to_dict().get('label')
            elif product.skus.filter_by(status=1).count() > 0:
                return {'status': 400, 'msg': f'商品 {product.name} 有多规格，请传 sku_id'}
            line_total = money_mul(unit_price, number)
            total_price = money_add(total_price, line_total)
            total_number += number
            line_rows.append((product, number, unit_price, line_total, sku_id, sku_label))

        from flask import g
        from flask_shop.utils.sms import normalize_phone

        # 代客下单：可按手机号绑定/创建买家
        customer_id = body.get('customer_id')
        phone = normalize_phone(body.get('customer_phone') or body.get('phone'))
        nickname = (body.get('customer_nickname') or body.get('nickname') or '').strip() or None
        contact_name = (body.get('contact_name') or '').strip()
        contact_phone = normalize_phone(body.get('contact_phone')) or phone
        if phone and not customer_id:
            customer = models.Customer.query.filter_by(tenant_id=tenant_id, phone=phone).first()
            if not customer:
                customer = models.Customer(
                    tenant_id=tenant_id,
                    phone=phone,
                    nickname=nickname or f'用户{phone[-4:]}',
                    status=1,
                )
                db.session.add(customer)
                db.session.flush()
            elif nickname and not customer.nickname:
                customer.nickname = nickname
            customer_id = customer.id
        if customer_id:
            # 校验归属本租户
            c_ok = models.Customer.query.filter_by(id=customer_id, tenant_id=tenant_id).first()
            if not c_ok:
                return {'status': 400, 'msg': '买家不存在或不属于本店'}

        # 地址拼接收件人信息，便于发货
        address = (address or '').strip()
        if contact_name or contact_phone:
            head = f"{contact_name or ''} {contact_phone or ''}".strip()
            if head and head not in address:
                address = f"{head} {address}".strip()
        if not address:
            return {'status': 400, 'msg': '请填写收货地址'}

        goods_amount = money_float(total_price)
        freight_amount, tpl = calc_order_freight(
            tenant_id, goods_amount, total_number, body.get('freight_template_id')
        )
        order = models.Order(
            tenant_id=tenant_id,
            order_no=_gen_order_no(tenant_id),
            price=money_float(money_add(goods_amount, freight_amount)),
            goods_amount=goods_amount,
            freight_amount=freight_amount,
            freight_template_id=tpl.id if tpl else None,
            number=total_number,
            status=PENDING_PAY,
            pay_status=0,
            is_send=0,
            address=address,
            fapiao_title=body.get('fapiao_title'),
            fapiao_content=body.get('fapiao_content'),
            uid=g.staff_id,
            customer_id=customer_id,
        )
        db.session.add(order)
        db.session.flush()

        try:
            for product, number, price, line_total, sku_id, sku_label in line_rows:
                dec_stock(tenant_id, product.id, number, sku_id=sku_id)
                detail = models.OrderDetail(
                    tenant_id=tenant_id,
                    oid=order.id,
                    pid=product.id,
                    sku_id=sku_id,
                    sku_label=sku_label,
                    number=number,
                    price=price,
                    total_price=line_total,
                )
                db.session.add(detail)
        except StockError as e:
            db.session.rollback()
            return {'status': 400, 'msg': e.message}

        db.session.commit()
        write_audit('order.create', 'order', order.id, f'no={order.order_no}')
        return {'status': 200, 'msg': '创建订单成功', 'data': order.to_dict()}


order_api.add_resource(Orders, '/orders/')


@order_bp.route('/orders/export/', methods=['GET'])
@login_required
def export_orders():
    """导出当前筛选条件下的订单 CSV（Excel 可直接打开）。"""
    from flask_shop.utils.rbac import staff_has_permission
    if not staff_has_permission('order:export'):
        return {'status': 403, 'msg': '无权限导出订单'}
    parser = reqparse.RequestParser()
    parser.add_argument('name', type=str, location='args')
    parser.add_argument('status', type=str, location='args')
    parser.add_argument('order_no', type=str, location='args')
    args = parser.parse_args()
    orders = _filter_orders_query(args).limit(5000).all()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        '订单ID', '订单号', '状态', '商品金额', '运费', '应付合计', '数量', '地址',
        '客户手机', '支付状态', '是否发货', '创建时间',
    ])
    for o in orders:
        writer.writerow([
            o.id,
            o.order_no or '',
            o.status or '',
            getattr(o, 'goods_amount', None) if getattr(o, 'goods_amount', None) is not None else o.price,
            getattr(o, 'freight_amount', None) or 0,
            o.price,
            o.number,
            o.address or '',
            o.customer.phone if o.customer else '',
            o.pay_status,
            o.is_send,
            o.create_time.strftime('%Y-%m-%d %H:%M:%S') if getattr(o, 'create_time', None) else '',
        ])

    write_audit('order.export', 'order', None, f'count={len(orders)} status={args.get("status") or "all"}')

    data = '﻿' + buf.getvalue()
    filename = f'orders_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
    return Response(
        data,
        mimetype='text/csv; charset=utf-8',
        headers={'Content-Disposition': f'attachment; filename={filename}'},
    )


@order_bp.route('/payments/export/', methods=['GET'])
@login_required
def export_payments():
    """
    对账导出：支付流水 CSV。
    查询参数：status / channel / days（默认 30，最大 365）
    """
    from datetime import timedelta
    from flask_shop.utils.rbac import staff_has_permission
    if not staff_has_permission('order:export'):
        return {'status': 403, 'msg': '无权限导出对账'}

    parser = reqparse.RequestParser()
    parser.add_argument('status', type=str, location='args')
    parser.add_argument('channel', type=str, location='args')
    parser.add_argument('days', type=int, location='args', default=30)
    args = parser.parse_args()

    tenant_id = require_tenant_id()
    days = args.get('days') or 30
    try:
        days = int(days)
    except (TypeError, ValueError):
        days = 30
    days = max(1, min(days, 365))
    since = datetime.now() - timedelta(days=days)

    q = models.Payment.query.filter(
        models.Payment.tenant_id == tenant_id,
        models.Payment.create_time >= since,
    )
    if args.get('status'):
        q = q.filter(models.Payment.status == args['status'])
    if args.get('channel'):
        q = q.filter(models.Payment.channel == args['channel'])
    payments = q.order_by(models.Payment.id.desc()).limit(10000).all()

    # 关联订单号
    order_ids = list({p.order_id for p in payments if p.order_id})
    order_map = {}
    if order_ids:
        for o in models.Order.query.filter(
            models.Order.tenant_id == tenant_id,
            models.Order.id.in_(order_ids),
        ).all():
            order_map[o.id] = o

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        '支付单ID', '商户支付单号', '渠道', '金额', '状态', '渠道流水号',
        '订单ID', '业务订单号', '订单状态', '支付时间', '创建时间',
    ])
    total_success = 0.0
    count_success = 0
    for p in payments:
        o = order_map.get(p.order_id)
        if p.status == 'success':
            total_success = money_add(total_success, p.amount or 0)
            count_success += 1
        writer.writerow([
            p.id,
            p.out_trade_no or '',
            p.channel or '',
            p.amount,
            p.status or '',
            p.transaction_id or '',
            p.order_id,
            o.order_no if o else '',
            o.status if o else '',
            p.paid_at.strftime('%Y-%m-%d %H:%M:%S') if p.paid_at else '',
            p.create_time.strftime('%Y-%m-%d %H:%M:%S') if getattr(p, 'create_time', None) else '',
        ])

    write_audit(
        'payment.export',
        'payment',
        None,
        f'count={len(payments)} success={count_success} amount={round(total_success, 2)} days={days}',
    )

    data = '﻿' + buf.getvalue()
    filename = f'payments_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
    return Response(
        data,
        mimetype='text/csv; charset=utf-8',
        headers={
            'Content-Disposition': f'attachment; filename={filename}',
            'X-Export-Count': str(len(payments)),
            'X-Export-Success-Amount': str(round(total_success, 2)),
        },
    )


@order_bp.route('/orders/summary/', methods=['GET'])
@login_required
def orders_summary():
    """发货台数字：各状态数量。"""
    from flask_shop.utils.rbac import staff_has_permission
    if not staff_has_permission('order:read'):
        return {'status': 403, 'msg': '无权限'}
    tenant_id = require_tenant_id()
    rows = db.session.query(models.Order.status, db.func.count(models.Order.id)).filter(
        models.Order.tenant_id == tenant_id
    ).group_by(models.Order.status).all()
    summary = {r[0] or 'unknown': r[1] for r in rows}
    return {
        'status': 200,
        'msg': 'ok',
        'data': {
            'by_status': summary,
            'pending_ship': summary.get('paid', 0),
            'pending_pay': summary.get('pending_pay', 0),
            'refunding': summary.get('refunding', 0),
            'total': sum(summary.values()),
        }
    }


@order_bp.route('/dashboard/kpi/', methods=['GET'])
@login_required
def dashboard_kpi():
    """
    工作台 / 数据页真实 KPI。
    返回：今日成交、待发货、待支付、售后中、在售商品、近7日趋势、状态分布。
    """
    from datetime import datetime, timedelta
    from flask_shop.utils.rbac import staff_has_permission

    if not (
        staff_has_permission('order:read')
        or staff_has_permission('report:read')
        or staff_has_permission('product:read')
    ):
        return {'status': 403, 'msg': '无权限查看数据'}

    tenant_id = require_tenant_id()
    closed_expired = 0
    try:
        from flask_shop.utils.order_timeout import close_expired_pending_orders
        closed_expired = close_expired_pending_orders(tenant_id=tenant_id)
    except Exception:
        current_app.logger.exception('dashboard auto-close expired orders failed')
    now = datetime.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    day7_start = today_start - timedelta(days=6)
    day30_start = today_start - timedelta(days=29)

    # 状态计数
    status_rows = db.session.query(
        models.Order.status, db.func.count(models.Order.id)
    ).filter(
        models.Order.tenant_id == tenant_id
    ).group_by(models.Order.status).all()
    by_status = {r[0] or 'unknown': r[1] for r in status_rows}

    # 今日：下单数 + 已支付金额（含 paid 及之后状态，按 paid_at 或 create_time）
    today_orders = models.Order.query.filter(
        models.Order.tenant_id == tenant_id,
        models.Order.create_time >= today_start,
    ).count()

    paid_like = ('paid', 'shipped', 'completed', 'refunding', 'refunded')
    today_gmv = db.session.query(
        db.func.coalesce(db.func.sum(models.Order.price), 0)
    ).filter(
        models.Order.tenant_id == tenant_id,
        models.Order.status.in_(paid_like),
        db.or_(
            models.Order.paid_at >= today_start,
            db.and_(models.Order.paid_at.is_(None), models.Order.create_time >= today_start),
        ),
    ).scalar() or 0

    # 近 7 日每日 GMV（已支付类）与下单数
    recent = models.Order.query.filter(
        models.Order.tenant_id == tenant_id,
        models.Order.create_time >= day7_start,
    ).all()
    trend_map = {}
    for i in range(7):
        d = (day7_start + timedelta(days=i)).strftime('%Y-%m-%d')
        trend_map[d] = {'date': d, 'orders': 0, 'gmv': 0.0}

    for o in recent:
        key = o.create_time.strftime('%Y-%m-%d') if o.create_time else None
        if not key or key not in trend_map:
            continue
        trend_map[key]['orders'] += 1
        if (o.status or '') in paid_like:
            trend_map[key]['gmv'] += float(o.price or 0)

    trend_7d = []
    for i in range(7):
        d = (day7_start + timedelta(days=i)).strftime('%Y-%m-%d')
        item = trend_map[d]
        item['gmv'] = round(item['gmv'], 2)
        trend_7d.append(item)

    # 在售 / 库存
    product_total = models.Product.query.filter_by(tenant_id=tenant_id).count()
    product_on = models.Product.query.filter(
        models.Product.tenant_id == tenant_id,
        db.or_(models.Product.state == 2, models.Product.state.is_(None)),
    ).count()
    low_stock = models.Product.query.filter(
        models.Product.tenant_id == tenant_id,
        models.Product.number.isnot(None),
        models.Product.number <= 5,
        db.or_(models.Product.state == 2, models.Product.state.is_(None)),
    ).count()

    # 状态分布（给饼图）
    status_labels = {
        'pending_pay': '待支付',
        'paid': '待发货',
        'shipped': '已发货',
        'completed': '已完成',
        'closed': '已关闭',
        'refunding': '售后中',
        'refunded': '已退款',
    }
    status_pie = [
        {'name': status_labels.get(k, k), 'value': v, 'status': k}
        for k, v in by_status.items() if v
    ]

    def _ord(o):
        return {
            'id': o.id,
            'order_no': o.order_no,
            'price': float(o.price or 0),
            'status': o.status,
            'buyer_paid_claimed': int(getattr(o, 'buyer_paid_claimed', 0) or 0),
            'buyer_paid_note': getattr(o, 'buyer_paid_note', None),
            'buyer_paid_at': o.buyer_paid_at.strftime('%Y-%m-%d %H:%M:%S') if getattr(o, 'buyer_paid_at', None) else None,
            'address': o.address,
        }

    claimed_q = (
        models.Order.query.filter_by(tenant_id=tenant_id, status='pending_pay', buyer_paid_claimed=1)
        .order_by(models.Order.buyer_paid_at.desc(), models.Order.id.desc())
        .limit(8).all()
    )
    pending_q = (
        models.Order.query.filter(
            models.Order.tenant_id == tenant_id,
            models.Order.status == 'pending_pay',
            db.or_(models.Order.buyer_paid_claimed.is_(None), models.Order.buyer_paid_claimed == 0),
        ).order_by(models.Order.id.desc()).limit(8).all()
    )
    ship_q = (
        models.Order.query.filter_by(tenant_id=tenant_id, status='paid')
        .order_by(models.Order.paid_at.desc(), models.Order.id.desc())
        .limit(8).all()
    )
    low_q = (
        models.Product.query.filter(
            models.Product.tenant_id == tenant_id,
            models.Product.number.isnot(None),
            models.Product.number <= 5,
            db.or_(models.Product.state == 2, models.Product.state.is_(None)),
        ).order_by(models.Product.number.asc()).limit(8).all()
    )
    claimed_pay_rows = [_ord(o) for o in claimed_q]
    pending_pay_rows = [_ord(o) for o in pending_q]
    pending_ship_rows = [_ord(o) for o in ship_q]
    low_stock_rows = [{'id': p.id, 'name': p.name, 'stock': int(p.number or 0)} for p in low_q]
    claimed_pay_n = models.Order.query.filter_by(
        tenant_id=tenant_id, status='pending_pay', buyer_paid_claimed=1
    ).count()

    # 老板视角：客服是否替代人工、是否促进成交、当前最该处理什么。
    traces = models.AgentTrace.query.filter(
        models.AgentTrace.tenant_id == tenant_id,
        models.AgentTrace.channel == 'mall_chat',
        models.AgentTrace.create_time >= day30_start,
    ).all()
    session_ids = {x.session_id for x in traces if x.session_id}
    transferred_sessions = {x.session_id for x in traces if x.session_id and (x.need_human or x.blocked)}
    ai_resolved_sessions = session_ids - transferred_sessions
    support_rows = models.SupportConversation.query.filter(
        models.SupportConversation.tenant_id == tenant_id,
        models.SupportConversation.create_time >= day30_start,
    ).all()
    first_response_minutes = [
        max((row.first_response_at - row.create_time).total_seconds() / 60, 0)
        for row in support_rows
        if row.first_response_at and row.create_time
    ]
    satisfaction_rows = [row.satisfaction for row in support_rows if row.satisfaction is not None]
    baseline_minutes = max(int(current_app.config.get('SUPPORT_BASELINE_MINUTES', 6)), 1)

    assisted_orders = models.Order.query.filter(
        models.Order.tenant_id == tenant_id,
        models.Order.create_time >= day30_start,
        models.Order.consultation_session_id.isnot(None),
        models.Order.consultation_session_id != '',
    ).all()
    assisted_paid = [row for row in assisted_orders if (row.status or '') in paid_like]
    assisted_gmv = round(sum(float(row.price or 0) for row in assisted_paid), 2)

    waiting_service = sum(1 for row in support_rows if row.status == 'waiting')
    active_service = sum(1 for row in support_rows if row.status == 'active')
    priority_items = []
    if claimed_pay_n:
        priority_items.append({
            'code': 'claimed_pay', 'level': 'urgent', 'count': claimed_pay_n,
            'title': '核对顾客已付款申报', 'detail': '核对到账后及时确认，避免顾客等待。',
            'route': '/order_list?status=pending_pay&claimed=1',
        })
    if waiting_service:
        priority_items.append({
            'code': 'support_waiting', 'level': 'urgent', 'count': waiting_service,
            'title': '接待等待中的顾客', 'detail': '人工队列正在等待，优先处理高风险和售后咨询。',
            'route': '/customer_service',
        })
    if by_status.get('paid', 0):
        priority_items.append({
            'code': 'pending_ship', 'level': 'warning', 'count': by_status.get('paid', 0),
            'title': '处理待发货订单', 'detail': '已确认收款，需进入发货流程。',
            'route': '/order_list?status=paid',
        })
    if by_status.get('refunding', 0):
        priority_items.append({
            'code': 'refunding', 'level': 'warning', 'count': by_status.get('refunding', 0),
            'title': '处理售后申请', 'detail': '退款和售后需要人工确认，避免升级为投诉。',
            'route': '/order_list?status=refunding',
        })
    if low_stock:
        priority_items.append({
            'code': 'low_stock', 'level': 'attention', 'count': low_stock,
            'title': '检查低库存商品', 'detail': '避免继续销售后出现缺货。',
            'route': '/product_list',
        })

    tenant = getattr(g, 'tenant', None)
    data_source = getattr(tenant, 'data_mode', None) or ('demo' if getattr(tenant, 'slug', None) == 'demo' else 'live')

    return {
        'status': 200,
        'msg': 'ok',
        'data': {
            'today': {
                'orders': today_orders,
                'gmv': round(float(today_gmv), 2),
            },
            'todo': {
                'pending_pay': by_status.get('pending_pay', 0),
                'pending_ship': by_status.get('paid', 0),
                'refunding': by_status.get('refunding', 0),
                'low_stock': low_stock,
                'claimed_pay': claimed_pay_n,
                'closed_expired': closed_expired,
            },
            'queues': {
                'claimed_pay': claimed_pay_rows,
                'pending_pay': pending_pay_rows,
                'pending_ship': pending_ship_rows,
                'low_stock': low_stock_rows,
            },
            'products': {
                'total': product_total,
                'on_sale': product_on,
                'low_stock': low_stock,
            },
            'orders_total': sum(by_status.values()),
            'by_status': by_status,
            'status_pie': status_pie,
            'trend_7d': trend_7d,
            'business': {
                'period_days': 30,
                'data_source': data_source,
                'generated_at': now.isoformat(timespec='seconds'),
                'service': {
                    'sessions': len(session_ids),
                    'ai_resolved': len(ai_resolved_sessions),
                    'transferred': len(transferred_sessions),
                    'ai_resolution_rate': round(len(ai_resolved_sessions) / len(session_ids) * 100, 1) if session_ids else None,
                    'estimated_saved_hours': round(len(ai_resolved_sessions) * baseline_minutes / 60, 1),
                    'baseline_minutes': baseline_minutes,
                    'waiting': waiting_service,
                    'active': active_service,
                    'avg_first_response_minutes': round(sum(first_response_minutes) / len(first_response_minutes), 1) if first_response_minutes else None,
                    'satisfaction': round(sum(satisfaction_rows) / len(satisfaction_rows), 1) if satisfaction_rows else None,
                    'rated_count': len(satisfaction_rows),
                },
                'conversion': {
                    'assisted_orders': len(assisted_orders),
                    'assisted_paid_orders': len(assisted_paid),
                    'assisted_gmv': assisted_gmv,
                    'method': 'explicit_session_id',
                },
                'priorities': priority_items[:5],
            },
        }
    }


class Order(Resource):
    method_decorators = [login_required]

    def get(self, id):
        from flask_shop.utils.rbac import staff_has_permission
        if not staff_has_permission('order:read'):
            return {'status': 403, 'msg': '无权限查看订单'}
        order = get_for_tenant(models.Order, id)
        if not order:
            return {'status': 404, 'msg': '订单不存在'}
        data = order.to_dict()
        data['payments'] = [p.to_dict() for p in order.payments.order_by(models.Payment.id.desc()).all()]
        return {'status': 200, 'msg': '获取订单详情成功', 'data': data}


order_api.add_resource(Order, '/order/<int:id>/')


def _do_transit(order_id, to_status, reason=None):
    order = get_for_tenant(models.Order, order_id)
    if not order:
        return None, ({'status': 404, 'msg': '订单不存在'}, 200)
    try:
        transit_order(order, to_status, reason=reason)
        db.session.commit()
        return order, None
    except OrderStateError as e:
        return None, ({'status': 400, 'msg': e.message}, 200)


@order_bp.route('/order/<int:id>/cancel/', methods=['POST'])
@login_required
def cancel_order(id):
    from flask_shop.utils.rbac import staff_has_permission
    if not staff_has_permission('order:cancel'):
        return {'status': 403, 'msg': '无权限取消订单'}
    order = get_for_tenant(models.Order, id)
    if not order:
        return {'status': 404, 'msg': '订单不存在'}
    body = request.get_json(silent=True) or {}
    reason = body.get('reason') or '用户取消'
    try:
        transit_order(order, CLOSED, reason=reason)
    except OrderStateError as e:
        return {'status': 400, 'msg': e.message}

    for d in order.order_detail or []:
        if d.pid and d.number:
            inc_stock(order.tenant_id, d.pid, d.number, sku_id=getattr(d, 'sku_id', None))
    db.session.commit()
    write_audit('order.cancel', 'order', order.id, reason)
    return {'status': 200, 'msg': '订单已关闭', 'data': order.to_dict()}


@order_bp.route('/order/<int:id>/mark-paid/', methods=['POST'])
@login_required
def mark_order_paid(id):
    """
    私有化无官方支付：店长核对线下收款后，将 pending_pay → paid。
    body: { note?: str }  备注写入审计，如「微信转账后四位 1234」
    """
    from flask_shop.utils.rbac import staff_has_permission
    from flask_shop.utils.order_state import PAID
    if not staff_has_permission('order:mark_paid'):
        return {'status': 403, 'msg': '无权限标记已付款'}
    order = get_for_tenant(models.Order, id)
    if not order:
        return {'status': 404, 'msg': '订单不存在'}
    if order.status != PENDING_PAY:
        return {'status': 400, 'msg': f'仅待支付订单可标记已付款，当前：{order.status}'}

    body = request.get_json(silent=True) or {}
    note = (body.get('note') or body.get('reason') or '').strip()

    try:
        transit_order(order, PAID)
    except OrderStateError as e:
        return {'status': 400, 'msg': e.message}

    # 记一笔人工支付单，便于详情里看到「怎么变成已付的」
    manual_no = f'M{order.tenant_id}{datetime.now().strftime("%Y%m%d%H%M%S")}{uuid.uuid4().hex[:6].upper()}'
    payment = models.Payment(
        tenant_id=order.tenant_id,
        order_id=order.id,
        out_trade_no=manual_no,
        channel='manual',
        amount=order.price,
        status='success',
        transaction_id=f'MANUAL{uuid.uuid4().hex[:12].upper()}',
        paid_at=datetime.now(),
        raw_notify=note or '店长标记已付款',
    )
    db.session.add(payment)
    db.session.commit()
    write_audit('order.mark_paid', 'order', order.id, note or 'manual paid')
    return {
        'status': 200,
        'msg': '已标记为已付款',
        'data': {
            'order': order.to_dict(),
            'payment': payment.to_dict(),
        }
    }


@order_bp.route('/order/<int:id>/ship/', methods=['POST'])
@login_required
def ship_order(id):
    from flask_shop.utils.rbac import staff_has_permission
    if not staff_has_permission('order:ship'):
        return {'status': 403, 'msg': '无权限发货'}
    order = get_for_tenant(models.Order, id)
    if not order:
        return {'status': 404, 'msg': '订单不存在'}
    try:
        transit_order(order, SHIPPED)
    except OrderStateError as e:
        return {'status': 400, 'msg': e.message}

    body = request.get_json(silent=True) or {}
    content = body.get('content') or body.get('express_content')
    if content:
        express = models.Express(
            tenant_id=order.tenant_id,
            oid=order.id,
            content=content,
            update_time=datetime.now(),
        )
        db.session.add(express)
    db.session.commit()
    write_audit('order.ship', 'order', order.id, content or '')
    return {'status': 200, 'msg': '发货成功', 'data': order.to_dict()}


@order_bp.route('/order/<int:id>/complete/', methods=['POST'])
@login_required
def complete_order(id):
    from flask_shop.utils.rbac import staff_has_permission
    if not staff_has_permission('order:complete'):
        return {'status': 403, 'msg': '无权限完成订单'}
    order, err = _do_transit(id, COMPLETED)
    if err:
        return err[0]
    write_audit('order.complete', 'order', order.id)
    return {'status': 200, 'msg': '订单已完成', 'data': order.to_dict()}


@order_bp.route('/order/<int:id>/refund/apply/', methods=['POST'])
@login_required
def apply_refund(id):
    from flask_shop.utils.rbac import staff_has_permission
    if not staff_has_permission('order:refund'):
        return {'status': 403, 'msg': '无权限操作售后'}
    order, err = _do_transit(id, REFUNDING)
    if err:
        return err[0]
    write_audit('order.refund_apply', 'order', order.id)
    return {'status': 200, 'msg': '已申请售后', 'data': order.to_dict()}


@order_bp.route('/order/<int:id>/refund/reject/', methods=['POST'])
@login_required
def reject_refund(id):
    from flask_shop.utils.rbac import staff_has_permission
    if not staff_has_permission('order:refund'):
        return {'status': 403, 'msg': '无权限操作售后'}
    order = get_for_tenant(models.Order, id)
    if not order:
        return {'status': 404, 'msg': '订单不存在'}
    if order.status != REFUNDING:
        return {'status': 400, 'msg': '当前状态不可拒绝售后'}
    from flask_shop.utils.order_state import PAID
    back = SHIPPED if order.is_send else PAID
    try:
        transit_order(order, back)
        db.session.commit()
    except OrderStateError as e:
        return {'status': 400, 'msg': e.message}
    write_audit('order.refund_reject', 'order', order.id, f'back={back}')
    return {'status': 200, 'msg': '已拒绝售后', 'data': order.to_dict()}


@order_bp.route('/order/<int:id>/refund/approve/', methods=['POST'])
@login_required
def approve_refund(id):
    from flask_shop.utils.rbac import staff_has_permission
    if not staff_has_permission('order:refund'):
        return {'status': 403, 'msg': '无权限操作售后'}
    order = get_for_tenant(models.Order, id)
    if not order:
        return {'status': 404, 'msg': '订单不存在'}
    if order.status != REFUNDING:
        return {'status': 400, 'msg': '仅售后中订单可同意退款'}

    body = request.get_json(silent=True) or {}
    reason = body.get('reason') or '商户同意退款'

    payment = (
        models.Payment.query.filter_by(tenant_id=order.tenant_id, order_id=order.id, status='success')
        .order_by(models.Payment.id.desc())
        .first()
    )

    refund = models.Refund(
        tenant_id=order.tenant_id,
        order_id=order.id,
        payment_id=payment.id if payment else None,
        out_refund_no=f'R{order.tenant_id}{datetime.now().strftime("%Y%m%d%H%M%S")}{uuid.uuid4().hex[:6].upper()}',
        amount=order.price,
        status='success',
        reason=reason,
        refunded_at=datetime.now(),
    )
    db.session.add(refund)

    try:
        transit_order(order, REFUNDED)
    except OrderStateError as e:
        return {'status': 400, 'msg': e.message}

    if payment:
        payment.status = 'refunded'

    for d in order.order_detail or []:
        if d.pid and d.number:
            inc_stock(order.tenant_id, d.pid, d.number, sku_id=getattr(d, 'sku_id', None))

    db.session.commit()
    write_audit('order.refund_approve', 'order', order.id, reason)
    return {
        'status': 200,
        'msg': '退款成功（模拟）',
        'data': {
            'order': order.to_dict(),
            'refund': refund.to_dict(),
        }
    }


class Expresses(Resource):
    method_decorators = [login_required]

    def get(self, id):
        order = get_for_tenant(models.Order, id)
        if not order:
            return {'status': 404, 'msg': '订单不存在'}
        express_list = models.Express.query.filter(
            models.Express.oid == id,
            models.Express.tenant_id == order.tenant_id,
        ).order_by(models.Express.update_time.desc()).all()

        return {
            'status': 200,
            'msg': '获取快递列表成功',
            'data': [express.to_dict() for express in express_list]
        }


order_api.add_resource(Expresses, '/expresses/<int:id>/')
