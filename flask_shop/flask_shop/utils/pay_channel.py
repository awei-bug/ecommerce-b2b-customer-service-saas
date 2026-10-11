"""
支付渠道抽象。

默认渠道由配置 PAY_DEFAULT_CHANNEL 决定：mock | wechat
- mock：仅开发/联调；生产若 ALLOW_MOCK_PAY!=1 则拒绝
- wechat：直连商户 API v3（wechatpayv3）；配置齐全时真下单，否则明确返回缺失项

密钥一律读环境变量，禁止写进代码仓库。
"""
import json
import logging
import os
import uuid
from abc import ABC, abstractmethod

from flask import current_app

logger = logging.getLogger(__name__)


class PayChannelError(Exception):
    def __init__(self, message, code=400):
        super().__init__(message)
        self.message = message
        self.code = code


class BaseChannel(ABC):
    name = 'base'

    @abstractmethod
    def prepay(self, payment, order, **kwargs):
        """
        发起预支付。
        返回 dict：channel, out_trade_no, pay_mode, client_payload, hint
        """

    def parse_notify(self, headers, body_raw):
        """解析并验签回调，返回 {out_trade_no, transaction_id, success, raw}"""
        raise PayChannelError(f'{self.name} 未实现回调')


class MockChannel(BaseChannel):
    name = 'mock'

    def prepay(self, payment, order, **kwargs):
        # fail-closed：配置缺失时一律拒绝，避免误放行 mock
        if not current_app.config.get('ALLOW_MOCK_PAY', False):
            raise PayChannelError('当前环境禁止 mock 支付', 403)
        payment.status = 'paying'
        return {
            'channel': 'mock',
            'out_trade_no': payment.out_trade_no,
            'pay_mode': 'mock',
            'client_payload': {
                'mock': True,
                'out_trade_no': payment.out_trade_no,
            },
            'hint': '开发环境：调用 POST /pay/mock/notify/ 或商城内「模拟支付」完成',
        }

    def parse_notify(self, headers, body_raw):
        data = body_raw if isinstance(body_raw, dict) else json.loads(body_raw or '{}')
        return {
            'out_trade_no': data.get('out_trade_no'),
            'transaction_id': data.get('transaction_id') or f'MOCK{uuid.uuid4().hex[:16].upper()}',
            'success': (data.get('result') or 'success').lower() != 'fail',
            'raw': data,
        }


def _read_private_key(path):
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


class WechatChannel(BaseChannel):
    """
    微信直连商户（Native / H5 / JSAPI）。

    环境变量：
      WECHAT_MCH_ID
      WECHAT_MCH_SERIAL_NO
      WECHAT_MCH_PRIVATE_KEY_PATH   apiclient_key.pem
      WECHAT_APP_ID
      WECHAT_API_V3_KEY
      WECHAT_NOTIFY_URL            公网 HTTPS，如 https://域名/pay/wechat/notify/
      WECHAT_PAY_TRADE_TYPE        native | h5 | jsapi
      WECHAT_CERT_DIR              可选，平台证书缓存目录
      WECHAT_PAYER_OPENID          JSAPI 默认 openid（也可下单时传 openid）
    """
    name = 'wechat'

    def _cfg(self):
        c = current_app.config
        return {
            'mch_id': c.get('WECHAT_MCH_ID') or '',
            'serial_no': c.get('WECHAT_MCH_SERIAL_NO') or '',
            'key_path': c.get('WECHAT_MCH_PRIVATE_KEY_PATH') or '',
            'app_id': c.get('WECHAT_APP_ID') or '',
            'api_v3_key': c.get('WECHAT_API_V3_KEY') or '',
            'notify_url': c.get('WECHAT_NOTIFY_URL') or '',
            'trade_type': (c.get('WECHAT_PAY_TRADE_TYPE') or 'native').lower(),
            'cert_dir': c.get('WECHAT_CERT_DIR') or '',
            'default_openid': c.get('WECHAT_PAYER_OPENID') or '',
        }

    def is_configured(self):
        cfg = self._cfg()
        missing = []
        for k in ('mch_id', 'serial_no', 'app_id', 'api_v3_key', 'notify_url'):
            if not cfg.get(k):
                missing.append(k)
        key_path = cfg.get('key_path') or ''
        if not key_path:
            missing.append('key_path')
        elif not os.path.isfile(key_path):
            missing.append('key_path(file_missing)')
        return len(missing) == 0, missing

    def _build_client(self, trade_type=None):
        try:
            from wechatpayv3 import WeChatPay, WeChatPayType
        except ImportError as e:
            raise PayChannelError(
                '未安装 wechatpayv3，请执行: pip install wechatpayv3',
                503,
            ) from e

        cfg = self._cfg()
        ok, missing = self.is_configured()
        if not ok:
            raise PayChannelError(f'微信配置不完整: {missing}', 503)

        tt = (trade_type or cfg['trade_type'] or 'native').lower()
        type_map = {
            'native': WeChatPayType.NATIVE,
            'h5': WeChatPayType.H5,
            'jsapi': WeChatPayType.JSAPI,
            'app': WeChatPayType.APP,
            'miniprogram': WeChatPayType.MINIPROG,
        }
        if tt not in type_map:
            raise PayChannelError(f'不支持的 WECHAT_PAY_TRADE_TYPE: {tt}')

        private_key = _read_private_key(cfg['key_path'])
        cert_dir = cfg['cert_dir'] or None
        if cert_dir:
            os.makedirs(cert_dir, exist_ok=True)

        client = WeChatPay(
            wechatpay_type=type_map[tt],
            mchid=cfg['mch_id'],
            private_key=private_key,
            cert_serial_no=cfg['serial_no'],
            apiv3_key=cfg['api_v3_key'],
            appid=cfg['app_id'],
            notify_url=cfg['notify_url'],
            cert_dir=cert_dir,
        )
        return client, tt, cfg

    def prepay(self, payment, order, **kwargs):
        amount_fen = int(round(float(payment.amount or 0) * 100))
        if amount_fen <= 0:
            raise PayChannelError('支付金额必须大于 0')

        ok, missing = self.is_configured()
        payment.status = 'paying'
        if not ok:
            return {
                'channel': 'wechat',
                'out_trade_no': payment.out_trade_no,
                'pay_mode': 'wechat_unconfigured',
                'client_payload': {
                    'configured': False,
                    'missing': missing,
                    'amount_fen': amount_fen,
                },
                'hint': (
                    '微信商户配置未齐全。请在 .env 填写 WECHAT_* 并放置 apiclient_key.pem。'
                    '本地联调可 PAY_DEFAULT_CHANNEL=mock 且 ALLOW_MOCK_PAY=1。'
                ),
            }

        trade_type = (kwargs.get('trade_type') or self._cfg()['trade_type'] or 'native').lower()
        client, tt, cfg = self._build_client(trade_type)

        description = (kwargs.get('description')
                       or f'订单{getattr(order, "order_no", None) or order.id}')
        description = str(description)[:127]

        pay_kwargs = {
            'description': description,
            'out_trade_no': payment.out_trade_no,
            'amount': {'total': amount_fen, 'currency': 'CNY'},
        }

        if tt in ('jsapi', 'miniprogram'):
            openid = kwargs.get('openid') or cfg.get('default_openid')
            if not openid:
                raise PayChannelError(
                    'JSAPI/小程序支付需要 payer openid（参数 openid 或 WECHAT_PAYER_OPENID）',
                    400,
                )
            pay_kwargs['payer'] = {'openid': openid}

        if tt == 'h5':
            # scene_info 可选；部分场景需要
            client_ip = kwargs.get('client_ip') or '127.0.0.1'
            pay_kwargs['scene_info'] = {
                'payer_client_ip': client_ip,
                'h5_info': {'type': 'Wap'},
            }

        try:
            code, message = client.pay(**pay_kwargs)
        except Exception as e:
            logger.exception('wechat pay error')
            raise PayChannelError(f'微信下单异常: {e}', 502) from e

        # wechatpayv3: code 是 HTTP 状态；message 可能是 dict 或 str
        if isinstance(message, (bytes, bytearray)):
            message = message.decode('utf-8', errors='replace')
        if isinstance(message, str):
            try:
                message = json.loads(message)
            except Exception:
                pass

        if code not in (200, 204) and not (isinstance(message, dict) and (
            message.get('code_url') or message.get('h5_url') or message.get('prepay_id')
        )):
            # 有的版本成功也返回 200 + body
            err_msg = message if isinstance(message, str) else json.dumps(message, ensure_ascii=False)
            # 若 message 含 code_url 仍视为成功
            if not (isinstance(message, dict) and (
                'code_url' in message or 'h5_url' in message or 'prepay_id' in message
            )):
                raise PayChannelError(f'微信下单失败 HTTP {code}: {err_msg}', 502)

        client_payload = {
            'configured': True,
            'trade_type': tt,
            'amount_fen': amount_fen,
            'out_trade_no': payment.out_trade_no,
        }
        hint = '请完成微信支付'
        pay_mode = f'wechat_{tt}'

        if isinstance(message, dict):
            if message.get('code_url'):
                client_payload['code_url'] = message['code_url']
                pay_mode = 'wechat_native'
                hint = '请使用微信扫描 code_url 对应二维码完成支付'
            if message.get('h5_url'):
                client_payload['h5_url'] = message['h5_url']
                pay_mode = 'wechat_h5'
                hint = '请引导用户打开 h5_url 完成支付'
            if message.get('prepay_id'):
                client_payload['prepay_id'] = message['prepay_id']
                # JSAPI 调起参数
                try:
                    # wechatpayv3 提供 sign 方法生成前端调起参数
                    if hasattr(client, 'sign'):
                        # 不同版本 API 略有差异
                        ts = str(int(__import__('time').time()))
                        nonce = uuid.uuid4().hex
                        pkg = f"prepay_id={message['prepay_id']}"
                        # JSAPI 签名字段
                        sign_data = [cfg['app_id'], ts, nonce, pkg]
                        pay_sign = client.sign(sign_data)
                        client_payload['jsapi'] = {
                            'appId': cfg['app_id'],
                            'timeStamp': ts,
                            'nonceStr': nonce,
                            'package': pkg,
                            'signType': 'RSA',
                            'paySign': pay_sign,
                        }
                        pay_mode = 'wechat_jsapi'
                        hint = '请使用 jsapi 参数调起微信支付'
                except Exception as e:
                    logger.warning('build jsapi payload failed: %s', e)
                    client_payload['jsapi_error'] = str(e)
            # 保留原始成功体键（脱敏）
            client_payload['raw_keys'] = list(message.keys())

        return {
            'channel': 'wechat',
            'out_trade_no': payment.out_trade_no,
            'pay_mode': pay_mode,
            'client_payload': client_payload,
            'hint': hint,
        }

    def parse_notify(self, headers, body_raw):
        ok, missing = self.is_configured()
        if not ok:
            raise PayChannelError(f'微信回调验签未就绪，缺少配置: {missing}', 503)

        client, _, _ = self._build_client()
        body = body_raw
        if isinstance(body, dict):
            body = json.dumps(body)
        if isinstance(body, str):
            body = body.encode('utf-8')

        # headers 需为普通 dict
        hdrs = dict(headers or {})
        try:
            result = client.callback(hdrs, body)
        except Exception as e:
            logger.exception('wechat callback verify failed')
            raise PayChannelError(f'微信回调验签失败: {e}', 400) from e

        if not result:
            raise PayChannelError('微信回调验签失败：空结果', 400)

        # result 通常已是解密后的 dict
        if isinstance(result, str):
            try:
                result = json.loads(result)
            except Exception:
                raise PayChannelError('微信回调解密结果无法解析', 400)

        # 兼容不同字段层级
        resource = result.get('resource') if isinstance(result.get('resource'), dict) else result
        event_type = result.get('event_type') or result.get('trade_state') or ''
        out_trade_no = (
            resource.get('out_trade_no')
            or result.get('out_trade_no')
        )
        transaction_id = (
            resource.get('transaction_id')
            or result.get('transaction_id')
        )
        trade_state = (
            resource.get('trade_state')
            or result.get('trade_state')
            or ''
        )

        success = trade_state == 'SUCCESS' or event_type in (
            'TRANSACTION.SUCCESS', 'SUCCESS',
        )
        # 部分 callback 实现直接返回解密业务数据且默认成功
        if not trade_state and not event_type and out_trade_no:
            success = True

        return {
            'out_trade_no': out_trade_no,
            'transaction_id': transaction_id,
            'success': bool(success),
            'raw': result,
            'trade_state': trade_state or event_type,
        }


def get_default_channel_name():
    return (current_app.config.get('PAY_DEFAULT_CHANNEL') or 'mock').lower()


def get_channel(name=None):
    name = (name or get_default_channel_name() or 'mock').lower()
    if name == 'mock':
        return MockChannel()
    if name in ('wechat', 'wx', 'weixin'):
        return WechatChannel()
    raise PayChannelError(f'不支持的支付渠道: {name}')
