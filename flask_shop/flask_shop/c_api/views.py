import json
from flask_shop.utils.rate_limit import rate_limit
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

from flask import current_app, g, request, session
from flask_restful import Resource
from sqlalchemy import or_

from flask_shop import db, models
from flask_shop.c_api import c_api, c_bp
from flask_shop.utils.tenant import bind_tenant, load_tenant, require_tenant_id
from flask_shop.utils.order_state import PENDING_PAY, OrderStateError
from flask_shop.utils.stock import StockError, dec_stock
from flask_shop.utils.freight import calc_order_freight
from flask_shop.utils.money import money_add, money_float, money_mul
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


_ATTRIBUTION_KEYS = ('campaign_id', 'content_id', 'product_id', 'source', 'medium', 'visitor_id')


def _clean_attribution(value):
    if not isinstance(value, dict):
        return {}
    return {
        key: str(value.get(key) or '').strip()[:128]
        for key in _ATTRIBUTION_KEYS
        if str(value.get(key) or '').strip()
    }


def _request_attribution(body=None):
    body = body or {}
    explicit = body.get('attribution') if isinstance(body.get('attribution'), dict) else body
    current = dict(session.get('growth_attribution') or {})
    current.update(_clean_attribution(explicit))
    return _clean_attribution(current)


def _landing_view_key(attribution):
    return '|'.join((
        attribution.get('campaign_id') or '',
        attribution.get('content_id') or '',
        attribution.get('product_id') or '',
    ))


@c_bp.before_request
def _c_bind_tenant():
    if request.method == 'OPTIONS':
        return None
    if request.path.rstrip('/').endswith('/api/c/ping'):
        return None
    tenant, err = _resolve_tenant_or_error()
    if err:
        return err[0], err[1]
    return None


def _tenant_has_pay_qr(tenant):
    if not tenant:
        return False
    return bool(
        (getattr(tenant, "pay_qr_wechat", None) or "").strip()
        or (getattr(tenant, "pay_qr_alipay", None) or "").strip()
    )


@c_bp.route('/ping/')
def ping():
    return {'status': 200, 'msg': 'c-api ok'}


@c_bp.route('/attribution/track/', methods=['GET', 'POST'])
def track_attribution():
    """保存推广来源；后续下单时复制到订单快照。"""
    body = request.get_json(silent=True) if request.method == 'POST' else request.args.to_dict()
    attribution = _request_attribution(body)
    if attribution.get('campaign_id') and not attribution.get('visitor_id'):
        attribution['visitor_id'] = f'visitor_{uuid.uuid4().hex}'
    tracked = False
    idempotent = False
    if attribution:
        session['growth_attribution'] = attribution
        view_key = _landing_view_key(attribution)
        tracked_views = list(session.get('growth_landing_views') or [])
        idempotent = bool(view_key and view_key in tracked_views)
        if view_key and not idempotent:
            try:
                from flask_shop.utils.growth_webhook import emit_landing_view_conversion
                tracked = bool(emit_landing_view_conversion(
                    attribution, require_tenant_id(), request.path))
                if tracked:
                    session['growth_landing_views'] = (tracked_views + [view_key])[-100:]
            except Exception as error:
                current_app.logger.warning('growth landing view emit failed: %s', error)
    return {
        'status': 200,
        'msg': '来源已记录',
        'data': attribution,
        'tracked': tracked,
        'idempotent': idempotent,
    }


def _lead_score(contact_name, demand, product_id, attribution):
    score = 25
    if contact_name:
        score += 15
    if len(demand) >= 10:
        score += 20
    if product_id:
        score += 20
    if attribution.get('campaign_id'):
        score += 20
    return min(score, 100)


@c_bp.route('/leads/', methods=['POST'])
@rate_limit(max_calls=5, per_seconds=60, prefix='growth_lead')
def create_growth_lead():
    body = request.get_json(silent=True) or {}
    contact_type = str(body.get('contact_type') or 'phone').strip().lower()
    if contact_type not in ('phone', 'wechat', 'email', 'other'):
        return {'status': 400, 'msg': '联系方式类型不支持'}, 400
    contact_value = str(body.get('contact_value') or '').strip()[:128]
    if not contact_value:
        return {'status': 400, 'msg': '请填写手机号、微信或邮箱'}, 400
    contact_name = str(body.get('contact_name') or '').strip()[:64]
    demand = str(body.get('demand') or '').strip()[:1000]
    product_id = body.get('product_id')
    product = None
    if product_id not in (None, ''):
        if not str(product_id).isdigit():
            return {'status': 400, 'msg': '商品参数无效'}, 400
        product = models.Product.query.filter_by(id=int(product_id), tenant_id=require_tenant_id()).first()
        if not product:
            return {'status': 404, 'msg': '商品不存在'}, 404
    attribution = _request_attribution(body)
    score = _lead_score(contact_name, demand, product.id if product else None, attribution)
    lead = models.GrowthLead(
        tenant_id=require_tenant_id(),
        product_id=product.id if product else None,
        campaign_id=attribution.get('campaign_id'),
        content_id=attribution.get('content_id'),
        source=attribution.get('source'),
        medium=attribution.get('medium'),
        visitor_id=attribution.get('visitor_id'),
        contact_name=contact_name,
        contact_type=contact_type,
        contact_value=contact_value,
        demand=demand,
        score=score,
        temperature='hot' if score >= 80 else 'warm' if score >= 55 else 'cold',
        consent=1 if body.get('consent', True) else 0,
    )
    db.session.add(lead)
    db.session.commit()
    try:
        from flask_shop.utils.growth_webhook import emit_lead_created_conversion
        emit_lead_created_conversion(lead)
    except Exception as error:
        current_app.logger.warning('growth lead emit failed: %s', error)
    return {'status': 200, 'msg': '咨询已提交，商家会尽快联系您', 'data': lead.to_dict()}, 201


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
                '【个人收款付款说明】\n'
                '1. 请扫码微信/支付宝个人收款码转账\n'
                '2. 金额与订单一致，备注务必填订单号\n'
                '3. 店长确认到账后发货（非官方自动扣款）'
            ),
            'contact_phone': getattr(tenant, 'contact_phone', None),
            'payment_mode': 'manual_qr',
            'pay_qr_wechat': getattr(tenant, 'pay_qr_wechat', None),
            'pay_qr_alipay': getattr(tenant, 'pay_qr_alipay', None),
            'has_pay_qr': bool(getattr(tenant, 'pay_qr_wechat', None) or getattr(tenant, 'pay_qr_alipay', None)),
            'tagline': '精选好物 · 确认收款后发货',
            'shipping_note': '下单后 48 小时内发货（节假日顺延）',
            'service_note': '支持订单查询与售后登记，问题请联系店主',
            'theme': getattr(tenant, 'theme', None) or 'retail',
        }
    }


# ---------- 登录 ----------

@c_bp.route('/auth/sms/send/', methods=['POST'])
@rate_limit(max_calls=10, per_seconds=60, prefix="sms_send")
def auth_sms_send():
    """
    发送登录验证码。
    body: { "phone": "13800138000" }
    开发模式：data.dev_code 为模拟短信验证码，前端应展示给用户。
    """
    body = request.get_json(silent=True) or {}
    phone = body.get('phone')
    tenant_id = require_tenant_id()
    payload, err = send_login_code(tenant_id, phone)
    if err:
        return {'status': 400, 'msg': err}
    phone_n = normalize_phone(phone)
    data = {
        'phone': phone_n,
        'expire_hint': '10分钟内有效',
        'cooldown': (payload or {}).get('cooldown') or 60,
        'dev_mode': bool((payload or {}).get('dev_mode')),
        'reused': bool((payload or {}).get('reused')),
    }
    # 开发模式把验证码回给前端（等同「收到短信」）
    code = (payload or {}).get('code')
    if code:
        data['dev_code'] = code
        data['mock_sms'] = f'【云购商城】您的登录验证码是 {code}，10分钟内有效。'
    msg = '验证码已发送'
    if data.get('dev_mode'):
        msg = '验证码已发送（开发模式：请查看页面上的模拟短信）'
    return {'status': 200, 'msg': msg, 'data': data}


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
        """商品列表：q 搜索；cid 一级分类；hot=1 热销。"""
        tenant_id = require_tenant_id()
        keyword = (request.args.get('q') or request.args.get('name') or '').strip()
        cid = request.args.get('cid') or request.args.get('cid_one')
        hot = (request.args.get('hot') or '').strip() in ('1', 'true', 'yes')
        limit = request.args.get('limit')
        q = models.Product.query.filter_by(tenant_id=tenant_id)
        q = q.filter(or_(models.Product.state == 2, models.Product.state.is_(None)))
        if keyword:
            like = f'%{keyword}%'
            q = q.filter(or_(
                models.Product.name.like(like),
                models.Product.introduce.like(like),
            ))
        if cid not in (None, '', '0', 'all'):
            try:
                cid_i = int(cid)
                q = q.filter(models.Product.cid_one == cid_i)
            except (TypeError, ValueError):
                pass
        if hot:
            q = q.order_by(models.Product.hot_number.desc(), models.Product.id.desc())
        else:
            q = q.order_by(models.Product.id.desc())
        if limit:
            try:
                q = q.limit(max(1, min(int(limit), 50)))
            except (TypeError, ValueError):
                pass
        items = q.all()
        data = []
        for p in items:
            data.append({
                'id': p.id,
                'name': p.name,
                'price': money_float(p.price),
                'number': p.number,
                'introduce': p.introduce,
                'big_img': p.big_img,
                'small_img': p.small_img,
                'cid_one': p.cid_one,
                'hot_number': getattr(p, 'hot_number', 0) or 0,
                'weight': float(getattr(p, 'weight', 0) or 0),
            })
        return {
            'status': 200,
            'msg': 'ok',
            'data': data,
            'keyword': keyword or None,
            'cid': cid or None,
        }


class CCategories(Resource):
    def get(self):
        """C 端分类（一级 + 可选二级）。"""
        tenant_id = require_tenant_id()
        rows = (
            models.Category.query.filter_by(tenant_id=tenant_id, level=1)
            .order_by(models.Category.id.asc())
            .all()
        )
        data = []
        for c in rows:
            children = (
                models.Category.query.filter_by(tenant_id=tenant_id, level=2, pid=c.id)
                .order_by(models.Category.id.asc())
                .all()
            )
            # 分类下商品数
            cnt = models.Product.query.filter_by(tenant_id=tenant_id, cid_one=c.id).filter(
                or_(models.Product.state == 2, models.Product.state.is_(None))
            ).count()
            data.append({
                'id': c.id,
                'name': c.name,
                'level': c.level,
                'product_count': cnt,
                'children': [{'id': ch.id, 'name': ch.name, 'level': 2} for ch in children],
            })
        return {'status': 200, 'msg': 'ok', 'data': data}


c_api.add_resource(CProducts, '/products/')
c_api.add_resource(CCategories, '/categories/')


class CProductDetail(Resource):
    def get(self, id):
        tenant_id = require_tenant_id()
        p = models.Product.query.filter_by(id=id, tenant_id=tenant_id).first()
        if not p:
            return {'status': 404, 'msg': '商品不存在'}
        data = {
            'id': p.id,
            'name': p.name,
            'price': money_float(p.price),
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
    from flask_shop.utils.coupon import coupon_effect, list_active_coupons, pick_best_coupon
    coupons = list_active_coupons(require_tenant_id())
    goods = money_float(body.get('goods_amount') or 0)
    best = pick_best_coupon(coupons, goods, fee)
    coupon_id = body.get('coupon_id')
    chosen = None
    if coupon_id not in (None, '', 0, '0'):
        chosen = next((c for c in coupons if int(c.id) == int(coupon_id)), None)
    elif coupon_id in (0, '0'):
        chosen = None
    else:
        chosen = best
    eff = coupon_effect(chosen, goods, fee) if chosen else {
        'eligible': False, 'discount': 0, 'freight': money_float(fee), 'save': 0, 'reason': None,
    }
    if chosen and not eff.get('eligible'):
        chosen = None
        eff = {'eligible': False, 'discount': 0, 'freight': money_float(fee), 'save': 0, 'reason': None}
    freight_out = money_float(eff['freight'] if chosen else fee)
    discount_out = money_float(eff.get('discount') or 0) if chosen else 0.0
    if chosen and (chosen.coupon_type or '') == 'shipping_free':
        pay = money_float(goods)
        freight_out = 0.0
    elif chosen:
        pay = money_float(money_add(goods, freight_out, -discount_out))
    else:
        pay = money_float(money_add(goods, fee))
    if pay < 0:
        pay = 0.0
    return {
        'status': 200,
        'msg': 'ok',
        'data': {
            'freight_amount': freight_out,
            'discount_amount': discount_out,
            'pay_amount': pay,
            'coupon': chosen.to_dict() if chosen else None,
            'coupons': [c.to_dict() for c in coupons],
            'template': tpl.to_dict() if tpl else None,
        }
    }


# ---------- 优惠券 ----------

@c_bp.route('/coupons/', methods=['GET'])
def c_list_coupons():
    from flask_shop.utils.coupon import list_active_coupons
    rows = list_active_coupons(require_tenant_id())
    return {'status': 200, 'msg': 'ok', 'data': [c.to_dict() for c in rows]}


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
    attribution = _request_attribution(body)
    items = body.get('items') or []
    if not items:
        return {'status': 400, 'msg': 'items 不能为空'}

    tenant_id = require_tenant_id()
    tenant = getattr(g, 'tenant', None)
    if tenant is None or getattr(tenant, 'id', None) != tenant_id:
        tenant = models.Tenant.query.get(tenant_id)
    if tenant is not None and getattr(tenant, 'status', 1) != 1:
        return {'status': 403, 'msg': '店铺暂停营业，暂不可下单'}
    if not _tenant_has_pay_qr(tenant):
        return {'status': 403, 'msg': '店主尚未上传收款码，暂不可下单'}
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
        # C 端：仅上架可售（state==2 或 null）
        st = getattr(product, 'state', None)
        if st is not None and int(st) != 2:
            return {'status': 400, 'msg': f'商品 {product.name} 未上架'}
        unit_price = money_float(product.price)
        sku_label = None
        if sku_id:
            sku = models.ProductSku.query.filter_by(
                id=sku_id, tenant_id=tenant_id, product_id=pid, status=1
            ).first()
            if not sku:
                return {'status': 400, 'msg': f'SKU {sku_id} 不存在或已停用'}
            unit_price = money_float(sku.price if sku.price is not None else product.price)
            sku_label = sku.to_dict().get('label')
        elif product.skus.filter_by(status=1).count() > 0:
            return {'status': 400, 'msg': f'商品 {product.name} 有多规格，请传 sku_id'}
        line_total = money_mul(unit_price, number)
        total_price = money_add(total_price, line_total)
        total_number += number
        line_rows.append((product, number, unit_price, line_total, sku_id, sku_label))

    goods_amount = money_float(total_price)
    freight_amount, tpl = calc_order_freight(
        tenant_id, goods_amount, total_number, body.get('freight_template_id')
    )
    from flask_shop.utils.coupon import coupon_effect, list_active_coupons, pick_best_coupon
    coupons = list_active_coupons(tenant_id)
    req_cid = body.get('coupon_id', None)
    chosen = None
    if req_cid in (0, '0'):
        chosen = None
    elif req_cid not in (None, ''):
        chosen = next((c for c in coupons if int(c.id) == int(req_cid)), None)
        if not chosen:
            return {'status': 400, 'msg': '优惠券不可用'}
    else:
        chosen = pick_best_coupon(coupons, goods_amount, freight_amount)
    eff = coupon_effect(chosen, goods_amount, freight_amount) if chosen else {
        'eligible': False, 'discount': 0.0, 'freight': money_float(freight_amount), 'save': 0.0,
    }
    if chosen and not eff.get('eligible'):
        return {'status': 400, 'msg': '未达到优惠券使用门槛'}
    freight_after = money_float(eff['freight'])
    discount_amount = money_float(eff.get('discount') or 0)
    if chosen and (chosen.coupon_type or '') == 'shipping_free':
        pay_amount = money_float(goods_amount)
        discount_amount = money_float(freight_amount)
        freight_after = 0.0
    else:
        pay_amount = money_float(money_add(goods_amount, freight_after, -discount_amount))
    if pay_amount < 0:
        pay_amount = 0.0

    order = models.Order(
        tenant_id=tenant_id,
        order_no=_gen_order_no(tenant_id),
        price=pay_amount,
        goods_amount=goods_amount,
        freight_amount=freight_after,
        discount_amount=discount_amount,
        coupon_id=chosen.id if chosen else None,
        freight_template_id=tpl.id if tpl else None,
        number=total_number,
        status=PENDING_PAY,
        pay_status=0,
        is_send=0,
        address=address_text,
        customer_id=g.customer_id,
        campaign_id=attribution.get('campaign_id'),
        content_id=attribution.get('content_id'),
        attribution_source=attribution.get('source'),
        attribution_medium=attribution.get('medium'),
        consultation_session_id=str(body.get('consultation_session_id') or '').strip()[:64] or None,
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
    try:
        from flask_shop.utils.growth_webhook import emit_order_created_conversion
        emit_order_created_conversion(order)
    except Exception as error:
        current_app.logger.warning('growth order created emit failed: %s', error)
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
    expresses = (
        models.Express.query.filter_by(tenant_id=tenant_id, oid=order.id)
        .order_by(models.Express.id.desc())
        .all()
    )
    data['express_list'] = [e.to_dict() for e in expresses]
    data['express'] = expresses[0].content if expresses else None
    data['express_content'] = data['express']
    return {'status': 200, 'msg': 'ok', 'data': data}


# ---------- 支付 ----------


def _save_pay_proof(file_storage, tenant_id):
    import os
    if not file_storage or not getattr(file_storage, "filename", None):
        return None, None
    name = str(file_storage.filename or "")
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext == "jpeg":
        ext = "jpg"
    if ext not in ("jpg", "png", "webp", "gif"):
        return None, "仅支持 jpg / png / webp / gif"
    file_storage.stream.seek(0, os.SEEK_END)
    size = file_storage.stream.tell()
    file_storage.stream.seek(0)
    max_bytes = int(current_app.config.get("MAX_UPLOAD_IMAGE_BYTES") or (5 * 1024 * 1024))
    if size <= 0:
        return None, "文件为空"
    if size > max_bytes:
        return None, "截图不能超过 5MB"
    folder = current_app.config.get("UPLOAD_FOLDER")
    sub = os.path.join(folder, str(tenant_id), "pay_proof")
    os.makedirs(sub, exist_ok=True)
    fname = uuid.uuid4().hex + "." + ext
    file_storage.save(os.path.join(sub, fname))
    return f"/static/upload/{tenant_id}/pay_proof/{fname}", None


@c_bp.route("/order/<int:id>/claim-paid/", methods=["POST"])
@customer_login_required
@rate_limit(max_calls=20, per_seconds=60, prefix="claim_paid")
def c_claim_paid(id):
    """顾客申报已付款（不改订单状态，店长仍需确认收款）。"""
    tenant_id = require_tenant_id()
    order = models.Order.query.filter_by(
        id=id, tenant_id=tenant_id, customer_id=g.customer_id
    ).first()
    if not order:
        return {"status": 404, "msg": "订单不存在"}
    if (order.status or "") != PENDING_PAY:
        return {"status": 400, "msg": "当前订单不是待付款状态"}

    body = request.get_json(silent=True) or {}
    note = (request.form.get("note") if request.form else None) or body.get("note") or ""
    note = str(note).strip()[:64]
    proof = getattr(order, "buyer_paid_proof", None)
    f = request.files.get("file") if request.files else None
    if f:
        rel, err = _save_pay_proof(f, tenant_id)
        if err:
            return {"status": 400, "msg": err}
        proof = rel

    order.buyer_paid_claimed = 1
    order.buyer_paid_at = datetime.utcnow()
    order.buyer_paid_note = note or order.buyer_paid_note
    order.buyer_paid_proof = proof
    db.session.commit()
    return {"status": 200, "msg": "已通知店长核对收款", "data": order.to_dict()}


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


# ---------- 购物车 ----------
@c_bp.route('/cart/', methods=['GET'])
@customer_login_required
def c_cart_list():
    from flask_shop import models
    items = models.CartItem.query.filter_by(tenant_id=g.tenant_id, customer_id=g.customer_id).all()
    return {'status': 200, 'msg': 'ok', 'data': [i.to_dict() for i in items]}


@c_bp.route('/cart/', methods=['POST'])
@customer_login_required
def c_cart_add():
    from flask_shop import db, models
    body = request.get_json(silent=True) or {}
    pid = int(body.get('product_id') or body.get('pid') or 0)
    qty = max(1, int(body.get('quantity') or body.get('number') or 1))
    sku_id = int(body.get('sku_id') or 0)
    if not pid:
        return {'status': 400, 'msg': 'product_id 必填'}
    p = models.Product.query.filter_by(id=pid, tenant_id=g.tenant_id).first()
    if not p:
        return {'status': 404, 'msg': '商品不存在'}
    row = models.CartItem.query.filter_by(
        tenant_id=g.tenant_id, customer_id=g.customer_id, product_id=pid, sku_id=sku_id
    ).first()
    if row:
        row.quantity = int(row.quantity or 0) + qty
    else:
        row = models.CartItem(
            tenant_id=g.tenant_id, customer_id=g.customer_id, product_id=pid, sku_id=sku_id, quantity=qty
        )
        db.session.add(row)
    db.session.commit()
    return {'status': 200, 'msg': '已加入购物车', 'data': row.to_dict()}


@c_bp.route('/cart/<int:item_id>/', methods=['PUT'])
@customer_login_required
def c_cart_update(item_id):
    from flask_shop import db, models
    body = request.get_json(silent=True) or {}
    row = models.CartItem.query.filter_by(id=item_id, tenant_id=g.tenant_id, customer_id=g.customer_id).first()
    if not row:
        return {'status': 404, 'msg': '购物车项不存在'}
    if 'quantity' in body or 'number' in body:
        q = int(body.get('quantity') or body.get('number') or 1)
        if q <= 0:
            db.session.delete(row)
        else:
            row.quantity = q
    db.session.commit()
    return {'status': 200, 'msg': 'ok'}


@c_bp.route('/cart/<int:item_id>/', methods=['DELETE'])
@customer_login_required
def c_cart_delete(item_id):
    from flask_shop import db, models
    row = models.CartItem.query.filter_by(id=item_id, tenant_id=g.tenant_id, customer_id=g.customer_id).first()
    if row:
        db.session.delete(row)
        db.session.commit()
    return {'status': 200, 'msg': 'ok'}


@c_bp.route('/checkout/preview/', methods=['POST'])
@customer_login_required
def c_checkout_preview():
    """按购物车商品试算国内运费。"""
    from flask_shop import models
    body = request.get_json(silent=True) or {}
    items = body.get('items') or []
    goods = 0.0
    pieces = 0
    lines = []
    for it in items:
        pid = int(it.get('pid') or it.get('product_id') or 0)
        num = max(1, int(it.get('number') or it.get('quantity') or 1))
        p = models.Product.query.filter_by(id=pid, tenant_id=g.tenant_id).first()
        if not p:
            continue
        price = float(p.price or 0)
        goods += price * num
        pieces += num
        lines.append({'pid': pid, 'name': p.name, 'number': num, 'price': price})
    freight, template = calc_order_freight(g.tenant_id, goods, pieces)
    payable = money_float(money_add(goods, freight))
    return {
        'status': 200,
        'msg': 'ok',
        'data': {
            'items': lines,
            'goods_amount': money_float(goods),
            'freight_amount': money_float(freight),
            'payable': payable,
            'template': template.to_dict() if template else None,
        },
    }
