"""
国际物流运单 POC API

内部：
  GET/POST /shipments/
  GET/PUT  /shipment/<id>/
  POST     /shipment/<id>/transit/     { to_status }
  POST     /shipment/<id>/events/      { content, location?, event_time? }
  GET      /shipments/summary/

客户只读查询（无需登录，需租户头）：
  GET /api/c/shipment/track/?no=SHxxx
"""
import uuid
from datetime import datetime

from flask import g, request
from flask_restful import Resource, reqparse

from flask_shop import db, models
from flask_shop.shipment import shipment_api, shipment_bp
from flask_shop.utils.audit import write_audit
from flask_shop.utils.rbac import staff_has_permission
from flask_shop.utils.shipment_state import (
    INQUIRY,
    SHIPMENT_STATUSES,
    ShipmentStateError,
    transit_shipment,
)
from flask_shop.utils.tenant import get_for_tenant, require_tenant_id, tenant_filter
from flask_shop.utils.token import login_required


def _gen_no(tenant_id):
    ts = datetime.now().strftime('%Y%m%d%H%M%S')
    return f'SH{tenant_id}{ts}{uuid.uuid4().hex[:5].upper()}'


def _parse_body():
    return request.get_json(silent=True) or {}


class Shipments(Resource):
    method_decorators = [login_required]

    def get(self):
        if not staff_has_permission('shipment:read'):
            return {'status': 403, 'msg': '无权限查看运单'}
        parser = reqparse.RequestParser()
        parser.add_argument('status', type=str, location='args')
        parser.add_argument('shipment_no', type=str, location='args')
        parser.add_argument('customer', type=str, location='args')
        parser.add_argument('q', type=str, location='args')
        args = parser.parse_args()

        q = tenant_filter(models.Shipment)
        if args.get('status'):
            q = q.filter(models.Shipment.status == args['status'])
        if args.get('shipment_no'):
            q = q.filter(models.Shipment.shipment_no == args['shipment_no'])
        if args.get('customer'):
            like = f"%{args['customer']}%"
            q = q.filter(models.Shipment.customer_name.like(like))
        if args.get('q'):
            like = f"%{args['q']}%"
            q = q.filter(
                db.or_(
                    models.Shipment.shipment_no.like(like),
                    models.Shipment.customer_name.like(like),
                    models.Shipment.origin.like(like),
                    models.Shipment.destination.like(like),
                    models.Shipment.bl_no.like(like),
                )
            )
        rows = q.order_by(models.Shipment.id.desc()).limit(200).all()
        return {
            'status': 200,
            'msg': 'ok',
            'data': [r.to_dict() for r in rows],
            'status_labels': SHIPMENT_STATUSES,
        }

    def post(self):
        if not staff_has_permission('shipment:write'):
            return {'status': 403, 'msg': '无权限创建运单'}
        body = _parse_body()
        tenant_id = require_tenant_id()
        sh = models.Shipment(
            tenant_id=tenant_id,
            shipment_no=_gen_no(tenant_id),
            status=body.get('status') or INQUIRY,
            customer_name=(body.get('customer_name') or '').strip() or None,
            customer_contact=(body.get('customer_contact') or '').strip() or None,
            customer_phone=(body.get('customer_phone') or '').strip() or None,
            customer_email=(body.get('customer_email') or '').strip() or None,
            transport_mode=(body.get('transport_mode') or 'sea').strip()[:16],
            origin=(body.get('origin') or '').strip() or None,
            destination=(body.get('destination') or '').strip() or None,
            incoterm=(body.get('incoterm') or '').strip() or None,
            cargo_desc=(body.get('cargo_desc') or '').strip() or None,
            packages=int(body.get('packages') or 0),
            weight_kg=float(body.get('weight_kg') or 0),
            volume_cbm=float(body.get('volume_cbm') or 0),
            quote_amount=float(body['quote_amount']) if body.get('quote_amount') not in (None, '') else None,
            currency=(body.get('currency') or 'USD').strip()[:8],
            bl_no=(body.get('bl_no') or '').strip() or None,
            remark=(body.get('remark') or '').strip() or None,
            owner_uid=g.staff_id,
        )
        if sh.status not in SHIPMENT_STATUSES:
            sh.status = INQUIRY
        db.session.add(sh)
        db.session.flush()
        # 创建节点
        ev = models.ShipmentEvent(
            tenant_id=tenant_id,
            shipment_id=sh.id,
            content='运单已创建',
            location=sh.origin,
            operator_uid=g.staff_id,
            event_time=datetime.now(),
        )
        db.session.add(ev)
        db.session.commit()
        write_audit('shipment.create', 'shipment', sh.id, sh.shipment_no)
        return {'status': 200, 'msg': '运单已创建', 'data': sh.to_dict(with_events=True, with_documents=True)}


shipment_api.add_resource(Shipments, '/shipments/')


class ShipmentDetail(Resource):
    method_decorators = [login_required]

    def get(self, id):
        if not staff_has_permission('shipment:read'):
            return {'status': 403, 'msg': '无权限查看运单'}
        sh = get_for_tenant(models.Shipment, id)
        if not sh:
            return {'status': 404, 'msg': '运单不存在'}
        return {'status': 200, 'msg': 'ok', 'data': sh.to_dict(with_events=True, with_documents=True)}

    def put(self, id):
        if not staff_has_permission('shipment:write'):
            return {'status': 403, 'msg': '无权限编辑运单'}
        sh = get_for_tenant(models.Shipment, id)
        if not sh:
            return {'status': 404, 'msg': '运单不存在'}
        body = _parse_body()
        for key in (
            'customer_name', 'customer_contact', 'customer_phone', 'customer_email',
            'transport_mode', 'origin', 'destination', 'incoterm',
            'cargo_desc', 'bl_no', 'remark', 'currency',
        ):
            if key in body:
                val = body.get(key)
                setattr(sh, key, (str(val).strip() if val is not None else None) or None)
        for key, cast in (
            ('packages', int),
            ('weight_kg', float),
            ('volume_cbm', float),
        ):
            if key in body and body.get(key) is not None:
                try:
                    setattr(sh, key, cast(body.get(key) or 0))
                except (TypeError, ValueError):
                    return {'status': 400, 'msg': f'{key} 不合法'}
        if 'quote_amount' in body:
            qa = body.get('quote_amount')
            if qa in (None, ''):
                sh.quote_amount = None
            else:
                try:
                    sh.quote_amount = float(qa)
                except (TypeError, ValueError):
                    return {'status': 400, 'msg': '报价金额不合法'}
        db.session.commit()
        write_audit('shipment.update', 'shipment', sh.id, sh.shipment_no)
        return {'status': 200, 'msg': '已保存', 'data': sh.to_dict(with_events=True, with_documents=True)}


shipment_api.add_resource(ShipmentDetail, '/shipment/<int:id>/')


DOC_TYPES = {
    'bl': '提单 B/L',
    'packing': '箱单',
    'invoice': '发票',
    'customs': '报关资料',
    'other': '其他',
}

ALLOWED_DOC_EXT = {
    'pdf', 'png', 'jpg', 'jpeg', 'gif', 'webp',
    'doc', 'docx', 'xls', 'xlsx', 'zip', 'rar',
}
MAX_DOC_BYTES = 15 * 1024 * 1024  # 15MB


def _secure_name(name):
    import re
    name = (name or 'file').replace('\\', '/').split('/')[-1]
    name = re.sub(r'[^\w.一-鿿\-]+', '_', name)
    return name[:180] or 'file'


@shipment_bp.route('/shipment/<int:id>/documents/', methods=['GET'])
@login_required
def list_documents(id):
    if not staff_has_permission('shipment:read'):
        return {'status': 403, 'msg': '无权限'}
    sh = get_for_tenant(models.Shipment, id)
    if not sh:
        return {'status': 404, 'msg': '运单不存在'}
    rows = models.ShipmentDocument.query.filter_by(
        tenant_id=sh.tenant_id, shipment_id=sh.id
    ).order_by(models.ShipmentDocument.id.desc()).all()
    return {
        'status': 200,
        'msg': 'ok',
        'data': [r.to_dict() for r in rows],
        'doc_types': DOC_TYPES,
    }


@shipment_bp.route('/shipment/<int:id>/documents/', methods=['POST'])
@login_required
def upload_document(id):
    """
    multipart/form-data:
      file: 必填
      doc_type: bl|packing|invoice|customs|other
      title: 可选
    """
    import os
    import uuid as uuidlib
    from flask import current_app

    if not staff_has_permission('shipment:write'):
        return {'status': 403, 'msg': '无权限上传附件'}
    sh = get_for_tenant(models.Shipment, id)
    if not sh:
        return {'status': 404, 'msg': '运单不存在'}

    f = request.files.get('file')
    if not f or not f.filename:
        return {'status': 400, 'msg': '请选择文件'}

    original = _secure_name(f.filename)
    ext = original.rsplit('.', 1)[-1].lower() if '.' in original else ''
    if ext not in ALLOWED_DOC_EXT:
        return {'status': 400, 'msg': f'不支持的文件类型，允许: {", ".join(sorted(ALLOWED_DOC_EXT))}'}

    # size check (werkzeug may stream; try content_length)
    f.stream.seek(0, os.SEEK_END)
    size = f.stream.tell()
    f.stream.seek(0)
    if size > MAX_DOC_BYTES:
        return {'status': 400, 'msg': '文件不能超过 15MB'}

    doc_type = (request.form.get('doc_type') or 'other').strip().lower()
    if doc_type not in DOC_TYPES:
        doc_type = 'other'
    title = (request.form.get('title') or '').strip() or original

    upload_root = current_app.config.get('UPLOAD_FOLDER')
    tenant_id = sh.tenant_id
    rel_dir = os.path.join(str(tenant_id), 'shipments', str(sh.id))
    abs_dir = os.path.join(upload_root, rel_dir)
    os.makedirs(abs_dir, exist_ok=True)

    stored = f'{uuidlib.uuid4().hex[:12]}_{original}'
    abs_path = os.path.join(abs_dir, stored)
    f.save(abs_path)

    web_path = f'/static/upload/{tenant_id}/shipments/{sh.id}/{stored}'.replace('\\', '/')
    doc = models.ShipmentDocument(
        tenant_id=tenant_id,
        shipment_id=sh.id,
        doc_type=doc_type,
        title=title[:128],
        file_name=original,
        path=web_path,
        size=size,
        mime=getattr(f, 'mimetype', None) or '',
        uploader_uid=g.staff_id,
    )
    db.session.add(doc)
    # 轨迹提示
    db.session.add(models.ShipmentEvent(
        tenant_id=tenant_id,
        shipment_id=sh.id,
        content=f'上传附件：{DOC_TYPES.get(doc_type, doc_type)} - {title}',
        operator_uid=g.staff_id,
        event_time=datetime.now(),
    ))
    db.session.commit()
    write_audit('shipment.doc_upload', 'shipment', sh.id, f'{doc_type}:{original}')
    return {
        'status': 200,
        'msg': '上传成功',
        'data': doc.to_dict(),
        'shipment': sh.to_dict(with_events=True, with_documents=True),
    }


@shipment_bp.route('/shipment/<int:sid>/documents/<int:did>/', methods=['DELETE'])
@login_required
def delete_document(sid, did):
    import os
    from flask import current_app

    if not staff_has_permission('shipment:write'):
        return {'status': 403, 'msg': '无权限删除附件'}
    sh = get_for_tenant(models.Shipment, sid)
    if not sh:
        return {'status': 404, 'msg': '运单不存在'}
    doc = models.ShipmentDocument.query.filter_by(
        id=did, tenant_id=sh.tenant_id, shipment_id=sh.id
    ).first()
    if not doc:
        return {'status': 404, 'msg': '附件不存在'}

    # 尝试删文件
    try:
        upload_root = current_app.config.get('UPLOAD_FOLDER')
        # path like /static/upload/{tid}/shipments/{id}/file
        rel = (doc.path or '').split('/static/upload/')[-1]
        abs_path = os.path.join(upload_root, rel.replace('/', os.sep))
        if os.path.isfile(abs_path):
            os.remove(abs_path)
    except Exception:
        pass

    db.session.delete(doc)
    db.session.commit()
    write_audit('shipment.doc_delete', 'shipment', sh.id, f'doc={did}')
    return {
        'status': 200,
        'msg': '已删除',
        'data': sh.to_dict(with_events=True, with_documents=True),
    }


@shipment_bp.route('/shipment/<int:id>/transit/', methods=['POST'])
@login_required
def shipment_transit(id):
    if not staff_has_permission('shipment:write'):
        return {'status': 403, 'msg': '无权限变更运单状态'}
    sh = get_for_tenant(models.Shipment, id)
    if not sh:
        return {'status': 404, 'msg': '运单不存在'}
    body = _parse_body()
    to_status = (body.get('to_status') or '').strip()
    if to_status not in SHIPMENT_STATUSES:
        return {'status': 400, 'msg': '未知状态', 'data': {'allowed': list(SHIPMENT_STATUSES.keys())}}
    try:
        transit_shipment(sh, to_status)
    except ShipmentStateError as e:
        return {'status': 400, 'msg': e.message}

    # 自动记一条轨迹
    note = (body.get('note') or '').strip()
    content = note or f'状态更新为：{SHIPMENT_STATUSES.get(to_status, to_status)}'
    ev = models.ShipmentEvent(
        tenant_id=sh.tenant_id,
        shipment_id=sh.id,
        content=content,
        location=(body.get('location') or '').strip() or None,
        operator_uid=g.staff_id,
        event_time=datetime.now(),
    )
    db.session.add(ev)
    db.session.commit()
    write_audit('shipment.transit', 'shipment', sh.id, f'{sh.shipment_no}->{to_status}')
    return {'status': 200, 'msg': '状态已更新', 'data': sh.to_dict(with_events=True, with_documents=True)}


@shipment_bp.route('/shipment/<int:id>/events/', methods=['POST'])
@login_required
def shipment_add_event(id):
    if not staff_has_permission('shipment:write'):
        return {'status': 403, 'msg': '无权限添加轨迹'}
    sh = get_for_tenant(models.Shipment, id)
    if not sh:
        return {'status': 404, 'msg': '运单不存在'}
    body = _parse_body()
    content = (body.get('content') or '').strip()
    if not content:
        return {'status': 400, 'msg': '轨迹内容不能为空'}
    event_time = datetime.now()
    if body.get('event_time'):
        try:
            event_time = datetime.fromisoformat(str(body.get('event_time')).replace('Z', ''))
        except ValueError:
            return {'status': 400, 'msg': 'event_time 格式应为 ISO 时间'}
    ev = models.ShipmentEvent(
        tenant_id=sh.tenant_id,
        shipment_id=sh.id,
        content=content[:512],
        location=(body.get('location') or '').strip() or None,
        operator_uid=g.staff_id,
        event_time=event_time,
    )
    db.session.add(ev)
    db.session.commit()
    write_audit('shipment.event', 'shipment', sh.id, content[:80])
    return {'status': 200, 'msg': '轨迹已添加', 'data': sh.to_dict(with_events=True, with_documents=True)}


@shipment_bp.route('/shipments/summary/', methods=['GET'])
@login_required
def shipments_summary():
    if not staff_has_permission('shipment:read'):
        return {'status': 403, 'msg': '无权限'}
    tenant_id = require_tenant_id()
    rows = db.session.query(
        models.Shipment.status, db.func.count(models.Shipment.id)
    ).filter(
        models.Shipment.tenant_id == tenant_id
    ).group_by(models.Shipment.status).all()
    by_status = {r[0] or 'unknown': r[1] for r in rows}
    return {
        'status': 200,
        'msg': 'ok',
        'data': {
            'by_status': by_status,
            'total': sum(by_status.values()),
            'in_transit': by_status.get('in_transit', 0),
            'inquiry': by_status.get('inquiry', 0),
            'labels': SHIPMENT_STATUSES,
        },
    }
