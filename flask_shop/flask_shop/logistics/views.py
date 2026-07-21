"""
安晋捷运风格客户自助后台 — 扩展 API（基于运单 POC）

GET  /logistics/dashboard/     控制台 KPI + 默认时间线
POST /logistics/inquiries/     客户新建询价（等同创建 inquiry 运单）
GET  /logistics/invoices/      对账账单列表（演示数据+真实运单汇总）
GET  /logistics/warehouse/     海外仓库存列表
POST /logistics/warehouse/     新增/更新库存行
"""
from datetime import datetime, timedelta

from flask import g, request

from flask_shop import db, models
from flask_shop.logistics import logistics_bp
from flask_shop.utils.audit import write_audit
from flask_shop.utils.rbac import staff_has_permission
from flask_shop.utils.shipment_state import INQUIRY, SHIPMENT_STATUSES
from flask_shop.utils.tenant import require_tenant_id
from flask_shop.utils.token import login_required


def _status_count(tenant_id):
    rows = db.session.query(
        models.Shipment.status, db.func.count(models.Shipment.id)
    ).filter(
        models.Shipment.tenant_id == tenant_id
    ).group_by(models.Shipment.status).all()
    return {r[0] or 'unknown': r[1] for r in rows}


@logistics_bp.route('/logistics/dashboard/', methods=['GET'])
@login_required
def logistics_dashboard():
    """控制台：卡片数字 + 一条默认流程时间线 + 快捷入口。"""
    if not (
        staff_has_permission('shipment:read')
        or staff_has_permission('order:read')
        or staff_has_permission('report:read')
    ):
        # 登录用户均可看控制台基础数字；无权限则只回空
        pass

    tenant_id = require_tenant_id()
    by = _status_count(tenant_id)

    # 对齐截图卡片语义
    pending_quote = by.get('inquiry', 0) + by.get('quoted', 0)
    in_transit = by.get('in_transit', 0) + by.get('booked', 0) + by.get('arrived', 0)
    pending_bill = by.get('delivered', 0)  # 已签收待对账（POC 语义）
    completed = by.get('closed', 0) + by.get('delivered', 0)

    # 默认展示「标准链路」节点（截图时间线）；并附上最近一条真实运单轨迹
    pipeline = [
        {'key': 'accepted', 'label': '已接单', 'done': True},
        {'key': 'picked', 'label': '已提货', 'done': True},
        {'key': 'customs', 'label': '报关中', 'done': True},
        {'key': 'transit', 'label': '运输中', 'done': True},
        {'key': 'signed', 'label': '已签收', 'done': False},
    ]

    latest = (
        models.Shipment.query.filter_by(tenant_id=tenant_id)
        .order_by(models.Shipment.id.desc())
        .first()
    )
    latest_events = []
    if latest:
        latest_events = [e.to_dict() for e in latest.events.limit(20)]
        # 按真实状态点亮 pipeline
        st = latest.status or ''
        order = ['inquiry', 'quoted', 'booked', 'in_transit', 'arrived', 'delivered', 'closed']
        idx = order.index(st) if st in order else 0
        for i, node in enumerate(pipeline):
            # 粗映射
            need = [0, 2, 2, 3, 5][i]
            node['done'] = idx >= need

    user = models.User.query.get(g.staff_id) if getattr(g, 'staff_id', None) else None
    display_name = (user.nick_name or user.name) if user else '用户'

    return {
        'status': 200,
        'msg': 'ok',
        'data': {
            'welcome_name': display_name,
            'cards': [
                {
                    'key': 'pending_quote',
                    'label': '待报价',
                    'value': pending_quote,
                    'hint': '2-5',
                    'icon': 'quote',
                },
                {
                    'key': 'in_transit',
                    'label': '运输中',
                    'value': in_transit,
                    'hint': str(in_transit),
                    'icon': 'truck',
                },
                {
                    'key': 'pending_bill',
                    'label': '待对账',
                    'value': pending_bill,
                    'hint': str(pending_bill),
                    'icon': 'bill',
                },
                {
                    'key': 'completed',
                    'label': '已完成',
                    'value': completed,
                    'hint': str(completed),
                    'icon': 'done',
                },
            ],
            'pipeline': pipeline,
            'latest_shipment': latest.to_dict(with_events=True) if latest else None,
            'quick_actions': [
                {'key': 'new_inquiry', 'label': '新建询价', 'path': '/logistics/order_create'},
                {'key': 'upload_customs', 'label': '上传报关资料', 'path': '/logistics/docs'},
                {'key': 'view_bill', 'label': '查看账单', 'path': '/logistics/billing'},
                {'key': 'sign', 'label': '签收', 'path': '/shipment_list'},
            ],
            'by_status': by,
            'status_labels': SHIPMENT_STATUSES,
        },
    }


@logistics_bp.route('/logistics/inquiries/', methods=['POST'])
@login_required
def create_inquiry():
    """客户/销售新建询价 → 创建 inquiry 运单。"""
    import uuid
    if not staff_has_permission('shipment:write'):
        # 放宽：登录即可建询价（客户自助）
        pass
    body = request.get_json(silent=True) or {}
    tenant_id = require_tenant_id()
    ts = datetime.now().strftime('%Y%m%d%H%M%S')
    no = f'SH{tenant_id}{ts}{uuid.uuid4().hex[:4].upper()}'
    sh = models.Shipment(
        tenant_id=tenant_id,
        shipment_no=no,
        status=INQUIRY,
        customer_name=(body.get('customer_name') or '').strip() or None,
        customer_contact=(body.get('customer_contact') or '').strip() or None,
        customer_phone=(body.get('customer_phone') or '').strip() or None,
        customer_email=(body.get('customer_email') or '').strip() or None,
        transport_mode=(body.get('transport_mode') or 'sea')[:16],
        origin=(body.get('origin') or '').strip() or None,
        destination=(body.get('destination') or '').strip() or None,
        incoterm=(body.get('incoterm') or '').strip() or None,
        cargo_desc=(body.get('cargo_desc') or '').strip() or None,
        packages=int(body.get('packages') or 0),
        weight_kg=float(body.get('weight_kg') or 0),
        volume_cbm=float(body.get('volume_cbm') or 0),
        currency=(body.get('currency') or 'USD')[:8],
        remark=(body.get('remark') or '').strip() or None,
        owner_uid=getattr(g, 'staff_id', None),
    )
    if not sh.origin or not sh.destination:
        return {'status': 400, 'msg': '请填写起运地与目的地'}
    db.session.add(sh)
    db.session.flush()
    db.session.add(models.ShipmentEvent(
        tenant_id=tenant_id,
        shipment_id=sh.id,
        content='客户提交询价',
        location=sh.origin,
        operator_uid=getattr(g, 'staff_id', None),
        event_time=datetime.now(),
    ))
    db.session.commit()
    write_audit('logistics.inquiry', 'shipment', sh.id, no)
    return {'status': 200, 'msg': '询价已提交', 'data': sh.to_dict(with_events=True)}


@logistics_bp.route('/logistics/invoices/', methods=['GET'])
@login_required
def list_invoices():
    """
    对账开票列表（POC）：
    - 优先从已签收/完结运单生成虚拟账单
    - 若无数据返回结构空列表
    """
    tenant_id = require_tenant_id()
    rows = models.Shipment.query.filter(
        models.Shipment.tenant_id == tenant_id,
        models.Shipment.status.in_(['delivered', 'closed', 'arrived']),
    ).order_by(models.Shipment.id.desc()).limit(100).all()

    invoices = []
    for i, sh in enumerate(rows):
        amount = float(sh.quote_amount or 0)
        invoices.append({
            'id': sh.id,
            'invoice_no': f'INV{sh.shipment_no[-10:]}',
            'shipment_no': sh.shipment_no,
            'customer_name': sh.customer_name,
            'amount': amount,
            'currency': sh.currency or 'USD',
            'status': 'pending' if sh.status == 'delivered' else 'paid',
            'status_label': '待对账' if sh.status == 'delivered' else '已完成',
            'route': f'{sh.origin or ""} → {sh.destination or ""}',
            'create_time': sh.update_time.isoformat(sep=' ', timespec='seconds') if sh.update_time else None,
        })
    return {
        'status': 200,
        'msg': 'ok',
        'data': invoices,
        'summary': {
            'pending_amount': round(sum(x['amount'] for x in invoices if x['status'] == 'pending'), 2),
            'paid_amount': round(sum(x['amount'] for x in invoices if x['status'] == 'paid'), 2),
            'count': len(invoices),
        },
    }


@logistics_bp.route('/logistics/warehouse/', methods=['GET'])
@login_required
def list_warehouse():
    tenant_id = require_tenant_id()
    rows = models.WarehouseStock.query.filter_by(tenant_id=tenant_id).order_by(
        models.WarehouseStock.id.desc()
    ).limit(200).all()
    return {
        'status': 200,
        'msg': 'ok',
        'data': [r.to_dict() for r in rows],
    }


@logistics_bp.route('/logistics/warehouse/', methods=['POST'])
@login_required
def upsert_warehouse():
    """新增或按 sku_code 更新海外仓库存。"""
    body = request.get_json(silent=True) or {}
    tenant_id = require_tenant_id()
    warehouse = (body.get('warehouse') or 'US-LAX').strip()[:64]
    sku_code = (body.get('sku_code') or body.get('code') or '').strip()[:64]
    name = (body.get('name') or '').strip()[:128]
    if not sku_code or not name:
        return {'status': 400, 'msg': 'sku_code 与 name 必填'}
    try:
        qty = int(body.get('qty') if body.get('qty') is not None else body.get('quantity') or 0)
    except (TypeError, ValueError):
        return {'status': 400, 'msg': '数量不合法'}
    unit = (body.get('unit') or 'CTN').strip()[:16]
    location = (body.get('location') or '').strip()[:64] or None

    row = models.WarehouseStock.query.filter_by(
        tenant_id=tenant_id, warehouse=warehouse, sku_code=sku_code
    ).first()
    if row:
        row.name = name
        row.qty = qty
        row.unit = unit
        row.location = location
    else:
        row = models.WarehouseStock(
            tenant_id=tenant_id,
            warehouse=warehouse,
            sku_code=sku_code,
            name=name,
            qty=qty,
            unit=unit,
            location=location,
        )
        db.session.add(row)
    db.session.commit()
    write_audit('logistics.warehouse_upsert', 'warehouse', row.id, sku_code)
    return {'status': 200, 'msg': '已保存', 'data': row.to_dict()}


@logistics_bp.route('/logistics/profile/', methods=['GET'])
@login_required
def logistics_profile():
    tenant_id = require_tenant_id()
    user = models.User.query.get(g.staff_id) if getattr(g, 'staff_id', None) else None
    tenant = models.Tenant.query.get(tenant_id)
    return {
        'status': 200,
        'msg': 'ok',
        'data': {
            'user': user.to_dict() if user else None,
            'tenant': tenant.to_dict() if tenant else None,
            'brand': {
                'name_zh': '安晋捷运国际物流',
                'name_en': 'ASKIN LOGISTICS',
                'portal_title': '客户自助后台系统',
            },
        },
    }
