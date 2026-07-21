from flask import request
from flask_restful import Resource

from flask_shop import db, models
from flask_shop.utils.token import login_required
from flask_shop.utils.tenant import get_for_tenant, require_tenant_id, tenant_filter
from flask_shop.utils.audit import write_audit

# 挂到 product 蓝图，少开一个 blueprint
from flask_shop.product import product_bp, product_api


@product_bp.route('/freight/templates/', methods=['GET'])
@login_required
def list_freight_templates():
    from flask_shop.utils.rbac import staff_has_permission
    if not staff_has_permission('product:read'):
        return {'status': 403, 'msg': '无权限'}
    rows = tenant_filter(models.FreightTemplate).order_by(
        models.FreightTemplate.is_default.desc(),
        models.FreightTemplate.id.desc(),
    ).all()
    return {'status': 200, 'msg': 'ok', 'data': [r.to_dict() for r in rows]}


@product_bp.route('/freight/templates/', methods=['POST'])
@login_required
def create_freight_template():
    from flask_shop.utils.rbac import staff_has_permission
    if not staff_has_permission('product:write'):
        return {'status': 403, 'msg': '无权限管理运费模板'}
    body = request.get_json(silent=True) or {}
    name = (body.get('name') or '').strip()
    if not name:
        return {'status': 400, 'msg': '模板名称必填'}
    tenant_id = require_tenant_id()
    charge_type = (body.get('charge_type') or 'fixed').lower()
    if charge_type not in ('free', 'fixed', 'by_piece'):
        return {'status': 400, 'msg': 'charge_type 须为 free/fixed/by_piece'}

    is_default = 1 if body.get('is_default') else 0
    if is_default:
        models.FreightTemplate.query.filter_by(tenant_id=tenant_id, is_default=1).update({'is_default': 0})

    # 若尚无任何模板，自动默认
    count = models.FreightTemplate.query.filter_by(tenant_id=tenant_id).count()
    if count == 0:
        is_default = 1

    row = models.FreightTemplate(
        tenant_id=tenant_id,
        name=name,
        charge_type=charge_type,
        fixed_fee=float(body.get('fixed_fee') or 0),
        first_piece=int(body.get('first_piece') or 1),
        first_fee=float(body.get('first_fee') or 0),
        additional_piece=int(body.get('additional_piece') or 1),
        additional_fee=float(body.get('additional_fee') or 0),
        free_amount=float(body.get('free_amount') or 0),
        is_default=is_default,
        status=1 if body.get('status', 1) else 0,
    )
    db.session.add(row)
    db.session.commit()
    write_audit('freight.create', 'freight', row.id, name)
    return {'status': 200, 'msg': '创建成功', 'data': row.to_dict()}


@product_bp.route('/freight/templates/<int:tid>/', methods=['PUT'])
@login_required
def update_freight_template(tid):
    from flask_shop.utils.rbac import staff_has_permission
    if not staff_has_permission('product:write'):
        return {'status': 403, 'msg': '无权限管理运费模板'}
    row = get_for_tenant(models.FreightTemplate, tid)
    if not row:
        return {'status': 404, 'msg': '模板不存在'}
    body = request.get_json(silent=True) or {}
    if body.get('name') is not None:
        row.name = (body.get('name') or '').strip() or row.name
    if body.get('charge_type') is not None:
        ct = (body.get('charge_type') or '').lower()
        if ct not in ('free', 'fixed', 'by_piece'):
            return {'status': 400, 'msg': 'charge_type 非法'}
        row.charge_type = ct
    for field in ('fixed_fee', 'first_fee', 'additional_fee', 'free_amount'):
        if body.get(field) is not None:
            setattr(row, field, float(body.get(field) or 0))
    for field in ('first_piece', 'additional_piece'):
        if body.get(field) is not None:
            setattr(row, field, int(body.get(field) or 1))
    if body.get('status') is not None:
        row.status = 1 if body.get('status') else 0
    if body.get('is_default'):
        models.FreightTemplate.query.filter_by(
            tenant_id=row.tenant_id, is_default=1
        ).update({'is_default': 0})
        row.is_default = 1
    db.session.commit()
    write_audit('freight.update', 'freight', row.id)
    return {'status': 200, 'msg': '已更新', 'data': row.to_dict()}


@product_bp.route('/freight/templates/<int:tid>/', methods=['DELETE'])
@login_required
def delete_freight_template(tid):
    from flask_shop.utils.rbac import staff_has_permission
    if not staff_has_permission('product:write'):
        return {'status': 403, 'msg': '无权限管理运费模板'}
    row = get_for_tenant(models.FreightTemplate, tid)
    if not row:
        return {'status': 404, 'msg': '模板不存在'}
    db.session.delete(row)
    db.session.commit()
    write_audit('freight.delete', 'freight', tid)
    return {'status': 200, 'msg': '已删除'}


@product_bp.route('/freight/preview/', methods=['POST'])
@login_required
def preview_freight():
    """试算运费 body: { goods_amount, total_pieces, template_id? }"""
    from flask_shop.utils.freight import calc_order_freight
    body = request.get_json(silent=True) or {}
    fee, tpl = calc_order_freight(
        require_tenant_id(),
        body.get('goods_amount') or 0,
        body.get('total_pieces') or 1,
        body.get('template_id'),
    )
    return {
        'status': 200,
        'msg': 'ok',
        'data': {
            'freight_amount': fee,
            'template': tpl.to_dict() if tpl else None,
        }
    }
