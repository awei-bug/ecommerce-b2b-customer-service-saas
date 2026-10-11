"""
C 端短信验证码

开发模式（SMS_DEV_MODE=1，默认）：
  - 不调用真实短信通道
  - 每次发送生成 6 位随机码写入数据库
  - 接口返回 dev_code，前端用「模拟短信」展示
  - 校验必须与库中未使用验证码一致（真正跑通发送→校验）

生产模式（SMS_DEV_MODE=0）：
  - 生成随机码，调用配置的短信通道发送
  - 响应不回传验证码
"""
import random
import re
from datetime import datetime, timedelta

from flask import current_app

from flask_shop import db, models

PHONE_RE = re.compile(r'^1[3-9]\d{9}$')


def normalize_phone(phone):
    phone = (phone or '').strip()
    if not PHONE_RE.match(phone):
        return None
    return phone


def is_dev_mode():
    return bool(current_app.config.get('SMS_DEV_MODE', True))


def _cooldown_seconds():
    # 开发模式缩短冷却，方便联调
    if is_dev_mode():
        return int(current_app.config.get('SMS_DEV_COOLDOWN', 10))
    return int(current_app.config.get('SMS_COOLDOWN', 60))


def send_login_code(tenant_id, phone):
    """
    生成并保存验证码。
    返回 (payload_or_None, error_msg)
    payload: {'code': str|None, 'cooldown': int, 'dev_mode': bool}
    """
    phone = normalize_phone(phone)
    if not phone:
        return None, '手机号不合法'

    cooldown = _cooldown_seconds()
    since = datetime.now() - timedelta(seconds=cooldown)
    recent = models.SmsCode.query.filter(
        models.SmsCode.tenant_id == tenant_id,
        models.SmsCode.phone == phone,
        models.SmsCode.scene == 'login',
        models.SmsCode.create_time >= since,
    ).order_by(models.SmsCode.id.desc()).first()

    # 冷却期内：开发模式直接回显同一条未使用验证码，避免「发不出去」的假失败
    if recent and not recent.used:
        if is_dev_mode():
            left = cooldown
            if recent.create_time:
                elapsed = (datetime.now() - recent.create_time).total_seconds()
                left = max(1, int(cooldown - elapsed))
            return {
                'code': recent.code,
                'cooldown': left,
                'dev_mode': True,
                'reused': True,
            }, None
        return None, f'发送过于频繁，请 {cooldown} 秒后再试'

    code = f'{random.randint(0, 999999):06d}'

    if not is_dev_mode():
        ok, err = _send_via_provider(phone, code)
        if not ok:
            return None, err or '短信发送失败'

    expires_min = int(current_app.config.get('SMS_CODE_EXPIRE_MINUTES', 10))
    row = models.SmsCode(
        tenant_id=tenant_id,
        phone=phone,
        code=code,
        scene='login',
        expires_at=datetime.now() + timedelta(minutes=expires_min),
        used=0,
    )
    db.session.add(row)
    db.session.commit()

    return {
        'code': code if is_dev_mode() else None,
        'cooldown': cooldown,
        'dev_mode': is_dev_mode(),
        'reused': False,
    }, None


def _send_via_provider(phone, code):
    """
    生产短信发送钩子。
    配置示例（.env）：
      SMS_DEV_MODE=0
      SMS_PROVIDER=console   # 或 aliyun / tencent（需自行填密钥实现）
    当前内置 console：把验证码打到服务端日志，便于无短信通道时自测。
    """
    provider = (current_app.config.get('SMS_PROVIDER') or 'console').strip().lower()
    if provider in ('console', 'log', 'stdout'):
        current_app.logger.warning('[SMS console] phone=%s code=%s', phone, code)
        print(f'[SMS console] 发送到 {phone} 验证码 {code}')
        return True, None

    if provider in ('http', 'webhook', 'custom'):
        # 通用 HTTP 短信网关：POST JSON {phone, code, scene}
        # 成功：HTTP 2xx，且 body 缺省或 ok/success 为真
        import json
        import urllib.error
        import urllib.request
        url = (current_app.config.get('SMS_HTTP_URL') or '').strip()
        if not url:
            return False, 'SMS_HTTP_URL 未配置'
        token = (current_app.config.get('SMS_HTTP_TOKEN') or '').strip()
        payload = {
            'phone': phone,
            'code': code,
            'scene': 'login',
            'sign': current_app.config.get('COMPANY_SHORT_NAME') or '云购商城',
        }
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        headers = {'Content-Type': 'application/json; charset=utf-8'}
        if token:
            headers['Authorization'] = f'Bearer {token}'
            headers['X-SMS-Token'] = token
        req = urllib.request.Request(url, data=body, headers=headers, method='POST')
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw = resp.read().decode('utf-8', 'replace')
                if not (200 <= resp.status < 300):
                    return False, f'短信网关 HTTP {resp.status}'
                if not raw.strip():
                    return True, None
                try:
                    data = json.loads(raw)
                except Exception:
                    return True, None  # 非 JSON 但 2xx 视为成功
                ok = data.get('ok')
                if ok is None:
                    ok = data.get('success')
                if ok is None:
                    ok = True
                if ok in (True, 1, '1', 'true', 'True', 'success', 'ok'):
                    return True, None
                return False, str(data.get('msg') or data.get('message') or '短信网关返回失败')
        except urllib.error.HTTPError as e:
            try:
                detail = e.read().decode('utf-8', 'replace')[:200]
            except Exception:
                detail = str(e)
            return False, f'短信网关 HTTP {e.code}: {detail}'
        except Exception as e:
            return False, f'短信网关失败: {e}'

    # 预留厂商名：请用 SMS_PROVIDER=http + 自建网关，或在此扩展
    # if provider == 'aliyun': ...
    # if provider == 'tencent': ...
    return False, f'未实现的短信通道 SMS_PROVIDER={provider}，可用 console/http 或 SMS_DEV_MODE=1'


def verify_login_code(tenant_id, phone, code):
    """校验成功返回 True，并标记 used。必须匹配数据库中的有效验证码。"""
    phone = normalize_phone(phone)
    code = (code or '').strip()
    if not phone or not code:
        return False, '手机号或验证码不能为空'
    if not re.fullmatch(r'\d{4,8}', code):
        return False, '验证码格式不正确'

    row = (
        models.SmsCode.query.filter(
            models.SmsCode.tenant_id == tenant_id,
            models.SmsCode.phone == phone,
            models.SmsCode.scene == 'login',
            models.SmsCode.used == 0,
            models.SmsCode.code == code,
        )
        .order_by(models.SmsCode.id.desc())
        .first()
    )
    if not row:
        return False, '验证码错误，请先获取验证码'
    if row.expires_at and row.expires_at < datetime.now():
        return False, '验证码已过期，请重新获取'
    row.used = 1
    db.session.commit()
    return True, None
