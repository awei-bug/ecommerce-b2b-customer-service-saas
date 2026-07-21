"""
支付模块

流程：
  1. POST /pay/create/              创建支付单并走渠道 prepay（默认 mock 或 wechat）
  2. POST /pay/mock/notify/         仅 mock 渠道；生产应关闭 ALLOW_MOCK_PAY
  3. POST /pay/wechat/notify/       微信回调入口（验签接入后启用）
  4. GET  /pay/<out_trade_no>/      查询支付单
  5. GET  /pay/channel/status/      当前渠道与配置是否齐全（不回传密钥）
"""
import json
import uuid
from datetime import datetime

from flask import current_app, request
from flask_restful import Resource

from flask_shop import db, models
from flask_shop.pay import pay_api, pay_bp
from flask_shop.utils.token import login_required
from flask_shop.utils.tenant import get_for_tenant, require_tenant_id
from flask_shop.utils.order_state import OrderStateError, PENDING_PAY, PAID, transit_order
from flask_shop.utils.pay_channel import PayChannelError, WechatChannel, get_channel, get_default_channel_name


def _gen_out_trade_no(tenant_id):
    ts = datetime.now().strftime('%Y%m%d%H%M%S')
    return f'P{tenant_id}{ts}{uuid.uuid4().hex[:8].upper()}'


def mark_payment_success(payment, transaction_id=None, raw_notify=None, commit=True):
    """幂等：已 success 直接返回；否则置 success 并推动订单 paid。"""
    if payment.status == 'success':
        return payment, False

    if payment.status in ('closed', 'refunded'):
        raise OrderStateError(f'支付单状态为 {payment.status}，不可支付成功')

    order = models.Order.query.filter_by(
        id=payment.order_id, tenant_id=payment.tenant_id
    ).first()
    if not order:
        raise OrderStateError('关联订单不存在')
    if order.status != PENDING_PAY:
        payment.status = 'closed'
        if commit:
            db.session.commit()
        raise OrderStateError(f'订单状态为 {order.status}，无法支付')

    payment.status = 'success'
    payment.transaction_id = transaction_id or f'TXN{uuid.uuid4().hex[:16].upper()}'
    payment.paid_at = datetime.now()
    if raw_notify is not None:
        payment.raw_notify = (
            raw_notify if isinstance(raw_notify, str)
            else json.dumps(raw_notify, ensure_ascii=False)
        )

    transit_order(order, PAID)
    if commit:
        db.session.commit()
    return payment, True


@pay_bp.route('/channel/status/', methods=['GET'])
@login_required
def channel_status():
    """查看当前支付配置（不含密钥明文）。"""
    default = get_default_channel_name()
    wx = WechatChannel()
    ok, missing = wx.is_configured()
    return {
        'status': 200,
        'msg': 'ok',
        'data': {
            'default_channel': default,
            'allow_mock_pay': bool(current_app.config.get('ALLOW_MOCK_PAY')),
            'wechat': {
                'configured': ok,
                'missing': missing,
                'trade_type': current_app.config.get('WECHAT_PAY_TRADE_TYPE'),
                'mch_id_set': bool(current_app.config.get('WECHAT_MCH_ID')),
                'app_id_set': bool(current_app.config.get('WECHAT_APP_ID')),
                'notify_url_set': bool(current_app.config.get('WECHAT_NOTIFY_URL')),
            },
        }
    }


@pay_bp.route('/create/', methods=['POST'])
@login_required
def create_payment():
    """
    body: { "order_id": 1, "channel": "mock"|"wechat" }  # channel 可省略，用默认
    """
    body = request.get_json(silent=True) or {}
    order_id = body.get('order_id')
    channel_name = (body.get('channel') or get_default_channel_name()).lower()
    if not order_id:
        return {'status': 400, 'msg': 'order_id 必填'}

    order = get_for_tenant(models.Order, order_id)
    if not order:
        return {'status': 404, 'msg': '订单不存在'}
    if order.status != PENDING_PAY:
        return {'status': 400, 'msg': f'仅待支付订单可发起支付，当前：{order.status}'}

    existing = (
        models.Payment.query.filter(
            models.Payment.tenant_id == order.tenant_id,
            models.Payment.order_id == order.id,
            models.Payment.status.in_(['created', 'paying']),
        )
        .order_by(models.Payment.id.desc())
        .first()
    )
    if existing:
        try:
            channel = get_channel(existing.channel or channel_name)
            prepay = channel.prepay(
                existing, order,
                openid=body.get('openid'),
                trade_type=body.get('trade_type'),
                client_ip=request.headers.get('X-Forwarded-For', request.remote_addr),
            )
        except PayChannelError as e:
            return {'status': e.code, 'msg': e.message}
        db.session.commit()
        return {
            'status': 200,
            'msg': '已有待支付单',
            'data': {
                'payment': existing.to_dict(),
                'prepay': prepay,
            }
        }

    try:
        channel = get_channel(channel_name)
    except PayChannelError as e:
        return {'status': e.code, 'msg': e.message}

    payment = models.Payment(
        tenant_id=require_tenant_id(),
        order_id=order.id,
        out_trade_no=_gen_out_trade_no(order.tenant_id),
        channel=channel.name,
        amount=order.price,
        status='created',
    )
    db.session.add(payment)
    db.session.flush()

    try:
        prepay = channel.prepay(
            payment, order,
            openid=body.get('openid'),
            trade_type=body.get('trade_type'),
            client_ip=request.headers.get('X-Forwarded-For', request.remote_addr),
        )
    except PayChannelError as e:
        db.session.rollback()
        return {'status': e.code, 'msg': e.message}

    db.session.commit()
    return {
        'status': 200,
        'msg': '支付单创建成功',
        'data': {
            'payment': payment.to_dict(),
            'prepay': prepay,
        }
    }


@pay_bp.route('/mock/notify/', methods=['POST'])
@login_required
def mock_notify():
    """
    模拟支付渠道回调（仅 ALLOW_MOCK_PAY=1 时可用）。
    body: { "out_trade_no": "P...", "result": "success"|"fail" }
    """
    if not current_app.config.get('ALLOW_MOCK_PAY', False):
        return {'status': 403, 'msg': '当前环境禁止 mock 支付'}

    body = request.get_json(silent=True) or {}
    out_trade_no = body.get('out_trade_no')
    result = (body.get('result') or 'success').lower()
    if not out_trade_no:
        return {'status': 400, 'msg': 'out_trade_no 必填'}

    tenant_id = require_tenant_id()
    payment = models.Payment.query.filter_by(
        tenant_id=tenant_id,
        out_trade_no=out_trade_no,
    ).first()
    if not payment:
        return {'status': 404, 'msg': '支付单不存在'}

    if result == 'fail':
        if payment.status == 'success':
            return {'status': 400, 'msg': '已支付成功，不能改为失败'}
        payment.status = 'failed'
        payment.raw_notify = json.dumps(body, ensure_ascii=False)
        db.session.commit()
        return {'status': 200, 'msg': '已标记支付失败', 'data': payment.to_dict()}

    try:
        payment, changed = mark_payment_success(payment, raw_notify=body)
    except OrderStateError as e:
        return {'status': 400, 'msg': e.message}

    order = get_for_tenant(models.Order, payment.order_id)
    return {
        'status': 200,
        'msg': '支付成功' if changed else '重复回调，已忽略',
        'data': {
            'payment': payment.to_dict(),
            'order': order.to_dict() if order else None,
            'idempotent': not changed,
        }
    }


@pay_bp.route('/wechat/notify/', methods=['POST'])
def wechat_notify():
    """
    微信支付结果通知（无需商户 JWT；必须验签解密）。
    成功必须返回 HTTP 200 + JSON {code:SUCCESS}，否则微信会重试。
    """
    from flask_shop.utils.audit import write_audit

    raw = request.get_data(as_text=True)
    headers = {k: v for k, v in request.headers.items()}
    try:
        channel = WechatChannel()
        parsed = channel.parse_notify(headers, raw)
    except PayChannelError as e:
        # 验签失败用 4xx/5xx，微信会重试；配置缺失亦然
        return {'code': 'FAIL', 'message': e.message}, (400 if e.code < 500 else 500)

    out_trade_no = parsed.get('out_trade_no')
    if not out_trade_no:
        return {'code': 'FAIL', 'message': 'no out_trade_no'}, 400

    payment = models.Payment.query.filter_by(out_trade_no=out_trade_no).first()
    if not payment:
        # 未知单号：仍回 SUCCESS 避免毒重试；记审计
        write_audit(
            'pay.wechat_notify_unknown', 'payment', out_trade_no,
            detail=str(parsed.get('trade_state') or '')[:200],
            actor_type='system',
        )
        return {'code': 'SUCCESS', 'message': '成功'}

    if not parsed.get('success'):
        if payment.status != 'success':
            payment.status = 'failed'
            payment.raw_notify = raw if isinstance(raw, str) else json.dumps(parsed.get('raw'), ensure_ascii=False)
            db.session.commit()
            write_audit(
                'pay.wechat_fail', 'payment', payment.id,
                detail=str(parsed.get('trade_state') or 'fail'),
                tenant_id=payment.tenant_id,
                actor_type='system',
            )
        return {'code': 'SUCCESS', 'message': '成功'}

    try:
        payment, changed = mark_payment_success(
            payment,
            transaction_id=parsed.get('transaction_id'),
            raw_notify=parsed.get('raw') or raw,
        )
        if changed:
            write_audit(
                'pay.wechat_success', 'payment', payment.id,
                detail=f'no={out_trade_no}',
                tenant_id=payment.tenant_id,
                actor_type='system',
            )
    except OrderStateError as e:
        # 幂等或状态冲突：告知微信成功，避免重复推送
        write_audit(
            'pay.wechat_idempotent', 'payment', payment.id,
            detail=str(e.message)[:200],
            tenant_id=payment.tenant_id,
            actor_type='system',
        )
    return {'code': 'SUCCESS', 'message': '成功'}


@pay_bp.route('/wechat/query/<string:out_trade_no>/', methods=['GET'])
@login_required
def wechat_query(out_trade_no):
    """
    主动查单（商户后台/补偿用）。
    若微信侧已支付而本地未更新，则补 mark_payment_success。
    """
    from flask_shop.utils.rbac import staff_has_permission
    if not staff_has_permission('order:read'):
        return {'status': 403, 'msg': '无权限'}

    tenant_id = require_tenant_id()
    payment = models.Payment.query.filter_by(
        tenant_id=tenant_id, out_trade_no=out_trade_no
    ).first()
    if not payment:
        return {'status': 404, 'msg': '支付单不存在'}

    if payment.status == 'success':
        return {
            'status': 200,
            'msg': '本地已支付',
            'data': {'payment': payment.to_dict(), 'synced': False},
        }

    ok, missing = WechatChannel().is_configured()
    if not ok:
        return {'status': 503, 'msg': f'微信未配置: {missing}'}

    try:
        client, _, _ = WechatChannel()._build_client()
        code, message = client.query(out_trade_no=out_trade_no)
        if isinstance(message, (bytes, bytearray)):
            message = message.decode('utf-8', errors='replace')
        if isinstance(message, str):
            try:
                message = json.loads(message)
            except Exception:
                pass
    except Exception as e:
        return {'status': 502, 'msg': f'查单失败: {e}'}

    trade_state = ''
    transaction_id = None
    if isinstance(message, dict):
        trade_state = message.get('trade_state') or ''
        transaction_id = message.get('transaction_id')

    synced = False
    if trade_state == 'SUCCESS':
        try:
            payment, changed = mark_payment_success(
                payment,
                transaction_id=transaction_id,
                raw_notify=message,
            )
            synced = changed
        except OrderStateError as e:
            return {'status': 400, 'msg': e.message, 'data': {'remote': message}}

    return {
        'status': 200,
        'msg': 'ok',
        'data': {
            'payment': payment.to_dict(),
            'remote_trade_state': trade_state,
            'synced': synced,
            'remote': message if isinstance(message, dict) else {'raw': message},
        },
    }


class PaymentDetail(Resource):
    method_decorators = [login_required]

    def get(self, out_trade_no):
        tenant_id = require_tenant_id()
        payment = models.Payment.query.filter_by(
            tenant_id=tenant_id,
            out_trade_no=out_trade_no,
        ).first()
        if not payment:
            return {'status': 404, 'msg': '支付单不存在'}
        return {'status': 200, 'msg': 'ok', 'data': payment.to_dict()}


pay_api.add_resource(PaymentDetail, '/<string:out_trade_no>/')
