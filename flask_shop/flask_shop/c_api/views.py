"""
C 端 API

约定：
  - 请求带租户：Header X-Tenant-Slug 或 ?tenant_slug=
  - 买家：Customer JWT（typ=customer），请求头 token 或 X-Customer-Token
  - 商品浏览可匿名；下单/支付/地址/我的订单需登录
  - 兼容：未登录时旧 Header X-Customer-Name 仅用于演示，新路径请登录
"""
import uuid
from datetime import datetime

from flask import g, request
from flask_restful import Resource
from sqlalchemy import or_

from flask_shop import db, models
from flask_shop.c_api import c_api, c_bp
from flask_shop.utils.tenant import bind_tenant, load_tenant, require_tenant_id
from flask_shop.utils.order_state import PENDING_PAY, OrderStateError
from flask_shop.utils.stock import StockError, dec_stock
from flask_shop.utils.freight import calc_order_freight
from flask_shop.utils.pay_channel import PayChannelError, get_channel, get_default_channel_name
from flask_shop.utils.token import (
    customer_login_required,
    generate_customer_token,
)
from flask_shop.utils.sms import normalize_phone, send_login_code, verify_login_code
from flask_shop.pay.views import mark_payment_success


def _resolve_tenant_or_error():
    slug = request.headers.get('X-Tenant-Slug') or request.args.get('tenant_slug')
    tid = request.headers.get('X-Tenant-Id') or request.args.get('tenant_id')
    tenant = load_tenant(
        tenant_id=int(tid) if tid and str(tid).isdigit() else None,
        tenant_slug=slug,
    )
    if not tenant:
        return None, ({'status': 400, 'msg': '租户不存在或未指定，请传 X-Tenant-Slug'}, 400)
    bind_tenant(tenant)
    return tenant, None


def _gen_order_no(tenant_id):
    ts = datetime.now().strftime('%Y%m%d%H%M%S')
    return f'C{tenant_id}{ts}{uuid.uuid4().hex[:6].upper()}'


def _gen_out_trade_no(tenant_id):
    ts = datetime.now().strftime('%Y%m%d%H%M%S')
    return f'CP{tenant_id}{ts}{uuid.uuid4().hex[:8].upper()}'


@c_bp.before_request
def _c_bind_tenant():
    if request.path.rstrip('/').endswith('/api/c/ping'):
        return None
    tenant, err = _resolve_tenant_or_error()
    if err:
        return err[0], err[1]
    return None


@c_bp.route('/ping/')
def ping():
    return {'status': 200, 'msg': 'c-api ok'}


@c_bp.route('/shop/')
def shop_info():
    tenant = g.tenant
    open_for_business = bool(getattr(tenant, 'status', 1) == 1)
    return {
        'status': 200,
        'msg': 'ok',
        'data': {
            'id': tenant.id,
            'name': tenant.name,
            'slug': tenant.slug,
            'logo': tenant.logo,
            'status': getattr(tenant, 'status', 1),
            'open_for_business': open_for_business,
            'pay_guide': getattr(tenant, 'pay_guide', None) or (
                '下单后请按商家说明完成付款（如微信/支付宝转账）。'
                '商家确认到账后会更新订单为已付款并安排发货。'
            ),
            'contact_phone': getattr(tenant, 'contact_phone', None),
            'payment_mode': 'manual',  # 当前私有化默认人工确认收款
        }
    }


# ---------- 登录 ----------

@c_bp.route('/auth/sms/send/', methods=['POST'])
def auth_sms_send():
    """
    发送登录验证码。
    body: { "phone": "13800138000" }
    开发模式响应可能含 dev_code。
    """
    body = request.get_json(silent=True) or {}
    phone = body.get('phone')
    tenant_id = require_tenant_id()
    code, err = send_login_code(tenant_id, phone)
    if err:
        return {'status': 400, 'msg': err}
    data = {'phone': normalize_phone(phone), 'expire_hint': '10分钟内有效'}
    if code is not None:
        data['dev_code'] = code
        data['dev_mode'] = True
    return {'status': 200, 'msg': '验证码已发送', 'data': data}


@c_bp.route('/auth/sms/login/', methods=['POST'])
def auth_sms_login():
    """
    验证码登录；不存在则自动注册买家。
    body: { "phone", "code", "nickname"? }
    """
    body = request.get_json(silent=True) or {}
    phone = normalize_phone(body.get('phone'))
    code = body.get('code')
    nickname = (body.get('nickname') or '').strip() or None
    if not phone:
        return {'status': 400, 'msg': '手机号不合法'}

    tenant_id = require_tenant_id()
    ok, err = verify_login_code(tenant_id, phone, code)
    if not ok:
        return {'status': 400, 'msg': err or '验证码错误'}

    customer = models.Customer.query.filter_by(
        tenant_id=tenant_id, phone=phone
    ).first()
    if not customer:
        customer = models.Customer(
            tenant_id=tenant_id,
            phone=phone,
            nickname=nickname or f'用户{phone[-4:]}',
            status=1,
        )
        db.session.add(customer)
        db.session.commit()
    else:
        if customer.status != 1:
            return {'status': 403, 'msg': '账号已禁用'}
        if nickname and not customer.nickname:
            customer.nickname = nickname
            db.session.commit()

    token = generate_customer_token(customer)
    return {
        'status': 200,
        'msg': '登录成功',
        'data': {
            'token': token,
            'customer': customer.to_dict(),
            'tenant': g.tenant.to_dict() if g.tenant else None,
        }
    }


@c_bp.route('/auth/me/', methods=['GET'])
@customer_login_required
def auth_me():
    return {
        'status': 200,
        'msg': 'ok',
        'data': {
            'customer': g.customer.to_dict(),
            'tenant': g.tenant.to_dict() if g.tenant else None,
        }
    }


# ---------- 地址 ----------

@c_bp.route('/addresses/', methods=['GET'])
@customer_login_required
def list_addresses():
    rows = (
        models.CustomerAddress.query.filter_by(
            tenant_id=require_tenant_id(),
            customer_id=g.customer_id,
        )
        .order_by(models.CustomerAddress.is_default.desc(), models.CustomerAddress.id.desc())
        .all()
    )
    return {'status': 200, 'msg': 'ok', 'data': [r.to_dict() for r in rows]}


@c_bp.route('/addresses/', methods=['POST'])
@customer_login_required
def create_address():
    body = request.get_json(silent=True) or {}
    contact_name = (body.get('contact_name') or '').strip()
    contact_phone = normalize_phone(body.get('contact_phone') or body.get('phone'))
    region = (body.get('region') or '').strip()
    detail = (body.get('detail') or '').strip()
    is_default = 1 if body.get('is_default') else 0
    if not contact_name or not contact_phone or not detail:
        return {'status': 400, 'msg': '联系人、手机号、详细地址必填'}

    tenant_id = require_tenant_id()
    if is_default:
        models.CustomerAddress.query.filter_by(
            tenant_id=tenant_id, customer_id=g.customer_id, is_default=1
        ).update({'is_default': 0})

    row = models.CustomerAddress(
        tenant_id=tenant_id,
        customer_id=g.customer_id,
        contact_name=contact_name,
        contact_phone=contact_phone,
        region=region,
        detail=detail,
        is_default=is_default or 0,
    )
    # 若是第一条地址，自动默认
    count = models.CustomerAddress.query.filter_by(
        tenant_id=tenant_id, customer_id=g.customer_id
    ).count()
    if count == 0:
        row.is_default = 1

    db.session.add(row)
    db.session.commit()
    return {'status': 200, 'msg': '地址已保存', 'data': row.to_dict()}


@c_bp.route('/addresses/<int:aid>/', methods=['DELETE'])
@customer_login_required
def delete_address(aid):
    row = models.CustomerAddress.query.filter_by(
        id=aid,
        tenant_id=require_tenant_id(),
        customer_id=g.customer_id,
    ).first()
    if not row:
        return {'status': 404, 'msg': '地址不存在'}
    db.session.delete(row)
    db.session.commit()
    return {'status': 200, 'msg': '已删除'}


# ---------- 商品 ----------

class CProducts(Resource):
    def get(self):
        """支持 name 或 q 关键词，匹配商品名/简介。"""
        tenant_id = require_tenant_id()
        keyword = (request.args.get('q') or request.args.get('name') or '').strip()
        q = models.Product.query.filter_by(tenant_id=tenant_id)
        q = q.filter(or_(models.Product.state == 2, models.Product.state.is_(None)))
        if keyword:
            like = f'%{keyword}%'
            q = q.filter(or_(
                models.Product.name.like(like),
                models.Product.introduce.like(like),
            ))
        items = q.order_by(models.Product.id.desc()).all()
        data = [{
            'id': p.id,
            'name': p.name,
            'price': p.price,
            'number': p.number,
            'introduce': p.introduce,
            'big_img': p.big_img,
            'small_img': p.small_img,
        } for p in items]
        return {'status': 200, 'msg': 'ok', 'data': data, 'keyword': keyword or None}


c_api.add_resource(CProducts, '/products/')


class CProductDetail(Resource):
    def get(self, id):
        tenant_id = require_tenant_id()
        p = models.Product.query.filter_by(id=id, tenant_id=tenant_id).first()
        if not p:
            return {'status': 404, 'msg': '商品不存在'}
        data = {
            'id': p.id,
            'name': p.name,
            'price': p.price,
            'number': p.stock_total(),
            'introduce': p.introduce,
            'big_img': p.big_img,
            'small_img': p.small_img,
            'has_sku': p.skus.filter_by(status=1).count() > 0,
            'skus': [
                s.to_dict()
                for s in p.skus.filter_by(status=1).order_by(models.ProductSku.id.asc()).all()
            ],
        }
        return {
            'status': 200,
            'msg': 'ok',
            'data': data,
        }


c_api.add_resource(CProductDetail, '/product/<int:id>/')


@c_bp.route('/freight/preview/', methods=['POST'])
def c_freight_preview():
    """试算运费（可匿名）：body { goods_amount, total_pieces, template_id? }"""
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


# ---------- 订单 ----------

@c_bp.route('/orders/', methods=['POST'])
@customer_login_required
def c_create_order():
    """
    body: {
      items: [{pid, number}],
      address_id?: int,
      address?: str,   # 无 address_id 时可用纯文本
      contact_name?, contact_phone?
    }
    """
    body = request.get_json(silent=True) or {}
    items = body.get('items') or []
    if not items:
        return {'status': 400, 'msg': 'items 不能为空'}

    tenant = getattr(g, 'tenant', None)
    if tenant is not None and getattr(tenant, 'status', 1) != 1:
        return {'status': 403, 'msg': '店铺暂停营业，暂不可下单'}

    tenant_id = require_tenant_id()
    address_text = ''
    address_id = body.get('address_id')
    if address_id:
        addr = models.CustomerAddress.query.filter_by(
            id=address_id, tenant_id=tenant_id, customer_id=g.customer_id
        ).first()
        if not addr:
            return {'status': 400, 'msg': '收货地址不存在'}
        address_text = (
            f'{addr.contact_name} {addr.contact_phone} '
            f'{addr.region or ""}{addr.detail}'
        ).strip()
    else:
        address_text = (body.get('address') or '').strip()
        if not address_text:
            return {'status': 400, 'msg': '请填写收货地址或选择 address_id'}

    total_price = 0.0
    total_number = 0
    line_rows = []
    for it in items:
        pid = it.get('pid')
        number = int(it.get('number') or 0)
        sku_id = it.get('sku_id')
        if not pid or number <= 0:
            return {'status': 400, 'msg': '商品或数量不合法'}
        product = models.Product.query.filter_by(id=pid, tenant_id=tenant_id).first()
        if not product:
            return {'status': 404, 'msg': f'商品 {pid} 不存在'}
        unit_price = float(product.price)
        sku_label = None
        if sku_id:
            sku = models.ProductSku.query.filter_by(
                id=sku_id, tenant_id=tenant_id, product_id=pid, status=1
            ).first()
            if not sku:
                return {'status': 400, 'msg': f'SKU {sku_id} 不存在或已停用'}
            unit_price = float(sku.price if sku.price is not None else product.price)
            sku_label = sku.to_dict().get('label')
        elif product.skus.filter_by(status=1).count() > 0:
            return {'status': 400, 'msg': f'商品 {product.name} 有多规格，请传 sku_id'}
        line_total = unit_price * number
        total_price += line_total
        total_number += number
        line_rows.append((product, number, unit_price, line_total, sku_id, sku_label))

    goods_amount = round(total_price, 2)
    freight_amount, tpl = calc_order_freight(
        tenant_id, goods_amount, total_number, body.get('freight_template_id')
    )

    order = models.Order(
        tenant_id=tenant_id,
        order_no=_gen_order_no(tenant_id),
        price=round(goods_amount + freight_amount, 2),
        goods_amount=goods_amount,
        freight_amount=freight_amount,
        freight_template_id=tpl.id if tpl else None,
        number=total_number,
        status=PENDING_PAY,
        pay_status=0,
        is_send=0,
        address=address_text,
        customer_id=g.customer_id,
    )
    db.session.add(order)
    db.session.flush()

    try:
        for product, number, price, line_total, sku_id, sku_label in line_rows:
            dec_stock(tenant_id, product.id, number, sku_id=sku_id)
            db.session.add(models.OrderDetail(
                tenant_id=tenant_id,
                oid=order.id,
                pid=product.id,
                sku_id=sku_id,
                sku_label=sku_label,
                number=number,
                price=price,
                total_price=line_total,
            ))
    except StockError as e:
        db.session.rollback()
        return {'status': 400, 'msg': e.message}

    db.session.commit()
    return {'status': 200, 'msg': '下单成功', 'data': order.to_dict()}


@c_bp.route('/orders/', methods=['GET'])
@customer_login_required
def c_list_orders():
    tenant_id = require_tenant_id()
    orders = (
        models.Order.query.filter_by(
            tenant_id=tenant_id,
            customer_id=g.customer_id,
        )
        .order_by(models.Order.id.desc())
        .limit(50)
        .all()
    )
    return {'status': 200, 'msg': 'ok', 'data': [o.to_dict() for o in orders]}


@c_bp.route('/order/<int:id>/', methods=['GET'])
@customer_login_required
def c_order_detail(id):
    tenant_id = require_tenant_id()
    order = models.Order.query.filter_by(
        id=id, tenant_id=tenant_id, customer_id=g.customer_id
    ).first()
    if not order:
        return {'status': 404, 'msg': '订单不存在'}
    data = order.to_dict()
    data['payments'] = [
        p.to_dict() for p in models.Payment.query.filter_by(
            tenant_id=tenant_id, order_id=order.id
        ).order_by(models.Payment.id.desc()).all()
    ]
    return {'status': 200, 'msg': 'ok', 'data': data}


# ---------- 支付 ----------

@c_bp.route('/pay/create/', methods=['POST'])
@customer_login_required
def c_pay_create():
    body = request.get_json(silent=True) or {}
    order_id = body.get('order_id')
    if not order_id:
        return {'status': 400, 'msg': 'order_id 必填'}
    tenant_id = require_tenant_id()
    order = models.Order.query.filter_by(
        id=order_id, tenant_id=tenant_id, customer_id=g.customer_id
    ).first()
    if not order:
        return {'status': 404, 'msg': '订单不存在'}
    if order.status != PENDING_PAY:
        return {'status': 400, 'msg': f'仅待支付订单可支付，当前：{order.status}'}

    channel_name = (body.get('channel') or get_default_channel_name()).lower()
    existing = models.Payment.query.filter(
        models.Payment.tenant_id == tenant_id,
        models.Payment.order_id == order.id,
        models.Payment.status.in_(['created', 'paying']),
    ).order_by(models.Payment.id.desc()).first()
    if existing:
        try:
            channel = get_channel(existing.channel or channel_name)
            prepay = channel.prepay(existing, order)
        except PayChannelError as e:
            return {'status': e.code, 'msg': e.message}
        db.session.commit()
        return {
            'status': 200,
            'msg': '已有待支付单',
            'data': {'payment': existing.to_dict(), 'prepay': prepay},
        }

    try:
        channel = get_channel(channel_name)
    except PayChannelError as e:
        return {'status': e.code, 'msg': e.message}

    payment = models.Payment(
        tenant_id=tenant_id,
        order_id=order.id,
        out_trade_no=_gen_out_trade_no(tenant_id),
        channel=channel.name,
        amount=order.price,
        status='created',
    )
    db.session.add(payment)
    db.session.flush()
    try:
        prepay = channel.prepay(payment, order)
    except PayChannelError as e:
        db.session.rollback()
        return {'status': e.code, 'msg': e.message}
    db.session.commit()
    return {
        'status': 200,
        'msg': '支付单创建成功',
        'data': {'payment': payment.to_dict(), 'prepay': prepay},
    }


@c_bp.route('/pay/mock/', methods=['POST'])
@customer_login_required
def c_pay_mock():
    from flask import current_app
    if not current_app.config.get('ALLOW_MOCK_PAY', False):
        return {'status': 403, 'msg': '当前环境禁止 mock 支付'}

    body = request.get_json(silent=True) or {}
    out_trade_no = body.get('out_trade_no')
    if not out_trade_no:
        return {'status': 400, 'msg': 'out_trade_no 必填'}
    tenant_id = require_tenant_id()
    payment = models.Payment.query.filter_by(
        tenant_id=tenant_id, out_trade_no=out_trade_no
    ).first()
    if not payment:
        return {'status': 404, 'msg': '支付单不存在'}

    order = models.Order.query.filter_by(
        id=payment.order_id, tenant_id=tenant_id, customer_id=g.customer_id
    ).first()
    if not order:
        return {'status': 404, 'msg': '订单不存在'}

    try:
        payment, changed = mark_payment_success(payment, raw_notify=body)
    except OrderStateError as e:
        return {'status': 400, 'msg': e.message}

    order = models.Order.query.filter_by(id=payment.order_id, tenant_id=tenant_id).first()
    return {
        'status': 200,
        'msg': '支付成功' if changed else '已支付（幂等）',
        'data': {
            'payment': payment.to_dict(),
            'order': order.to_dict() if order else None,
            'idempotent': not changed,
        }
    }


@c_bp.route('/shipment/track/', methods=['GET'])
def c_shipment_track():
    """
    客户只读查轨迹（POC）。
    需要租户头 X-Tenant-Slug，查询参数 no=运单号。
    不要求买家登录（货主可分享运单号）。
    """
    tenant_id = require_tenant_id()
    no = (request.args.get('no') or request.args.get('shipment_no') or '').strip()
    if not no:
        return {'status': 400, 'msg': '请提供运单号 no'}
    sh = models.Shipment.query.filter_by(tenant_id=tenant_id, shipment_no=no).first()
    if not sh:
        return {'status': 404, 'msg': '未找到运单'}
    # 对外脱敏：不回传报价等敏感商务字段可选；POC 先返回主流程字段
    data = sh.to_dict(with_events=True, with_documents=True)
    data.pop('quote_amount', None)
    data.pop('owner_uid', None)
    data.pop('owner_name', None)
    data.pop('remark', None)
    return {'status': 200, 'msg': 'ok', 'data': data}

