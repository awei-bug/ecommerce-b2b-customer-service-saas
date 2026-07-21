"""运费计算工具。"""
from flask_shop import models


def get_default_template(tenant_id):
    tpl = models.FreightTemplate.query.filter_by(
        tenant_id=tenant_id, is_default=1, status=1
    ).first()
    if tpl:
        return tpl
    return models.FreightTemplate.query.filter_by(
        tenant_id=tenant_id, status=1
    ).order_by(models.FreightTemplate.id.asc()).first()


def resolve_template(tenant_id, template_id=None):
    if template_id:
        tpl = models.FreightTemplate.query.filter_by(
            id=template_id, tenant_id=tenant_id, status=1
        ).first()
        if tpl:
            return tpl
    return get_default_template(tenant_id)


def calc_order_freight(tenant_id, goods_amount, total_pieces, template_id=None):
    """
    返回 (freight_amount, template_or_None)
    无模板时运费 0（兼容旧店）。
    """
    tpl = resolve_template(tenant_id, template_id)
    if not tpl:
        return 0.0, None
    return tpl.calc_fee(goods_amount, total_pieces), tpl
