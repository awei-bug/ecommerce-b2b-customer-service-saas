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
import hashlib
import re
import secrets
from datetime import datetime, timedelta

from flask import current_app, request
from sqlalchemy import case, or_, update
from sqlalchemy.exc import IntegrityError

from flask_shop import db, models

PHONE_RE = re.compile(r'^1[3-9][0-9]{9}$')
SMS_LOCKED_MESSAGE = '验证码尝试次数过多，请稍后再试'
SMS_SEND_LIMIT_MESSAGE = '短信发送过于频繁，请稍后再试'


def normalize_phone(phone):
    phone = phone.strip() if isinstance(phone, str) else ''
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


def _ensure_throttle(scope, key):
    try:
        with db.session.begin_nested():
            db.session.add(models.LoginThrottle(scope=scope, key_hash=key, failed_count=0))
            db.session.flush()
    except IntegrityError:
        pass


def _reserve_send_slot(scope, value, limit, seconds, now):
    key = hashlib.sha256(value.encode('utf-8')).hexdigest()
    _ensure_throttle(scope, key)
    cutoff = now - timedelta(seconds=seconds)
    expired = or_(models.LoginThrottle.first_failed_at.is_(None),
                  models.LoginThrottle.first_failed_at <= cutoff)
    result = db.session.execute(update(models.LoginThrottle).where(
        models.LoginThrottle.scope == scope,
        models.LoginThrottle.key_hash == key,
        or_(expired, models.LoginThrottle.failed_count < limit),
    ).values(
        failed_count=case((expired, 1), else_=models.LoginThrottle.failed_count + 1),
        first_failed_at=case((expired, now), else_=models.LoginThrottle.first_failed_at),
        last_failed_at=now,
    ))
    return result.rowcount == 1


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
        if is_dev_mode() and recent.expires_at and recent.expires_at > datetime.now():
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
        return None, SMS_SEND_LIMIT_MESSAGE

    now = datetime.now()
    ip_limit = int(current_app.config.get('SMS_SEND_IP_LIMIT', 10))
    ip_window = int(current_app.config.get('SMS_SEND_IP_WINDOW_SECONDS', 60))
    if not _reserve_send_slot('sms_send_phone', phone, 1, cooldown, now) or not _reserve_send_slot(
        'sms_send_ip', request.remote_addr or 'unknown', ip_limit, ip_window, now,
    ):
        db.session.rollback()
        return None, SMS_SEND_LIMIT_MESSAGE
    db.session.commit()

    code = f'{secrets.randbelow(1000000):06d}'

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


def _reserve_login_attempt(tenant_id, phone, now):
    key = hashlib.sha256(f'{tenant_id}:{phone}'.encode('utf-8')).hexdigest()
    scope = 'sms_account'
    _ensure_throttle(scope, key)

    limit = int(current_app.config.get('SMS_LOGIN_ATTEMPT_LIMIT', 5))
    lock_minutes = int(current_app.config.get('SMS_LOGIN_LOCK_MINUTES', 15))
    cutoff = now - timedelta(minutes=lock_minutes)
    reset = or_(models.LoginThrottle.last_failed_at.is_(None),
                models.LoginThrottle.last_failed_at <= cutoff,
                models.LoginThrottle.locked_until <= now)
    next_count = case((reset, 1), else_=models.LoginThrottle.failed_count + 1)
    result = db.session.execute(update(models.LoginThrottle).where(
        models.LoginThrottle.scope == scope,
        models.LoginThrottle.key_hash == key,
        or_(models.LoginThrottle.locked_until.is_(None), models.LoginThrottle.locked_until <= now),
    ).values(
        failed_count=next_count,
        first_failed_at=case((reset, now), else_=models.LoginThrottle.first_failed_at),
        last_failed_at=now,
        locked_until=None,
    ))
    if result.rowcount != 1:
        return None
    db.session.execute(update(models.LoginThrottle).where(
        models.LoginThrottle.scope == scope,
        models.LoginThrottle.key_hash == key,
        models.LoginThrottle.failed_count >= limit,
    ).values(locked_until=now + timedelta(minutes=lock_minutes)))
    return key


def verify_login_code(tenant_id, phone, code):
    """限制每个店铺手机号的尝试，并原子消费最新验证码。"""
    phone = normalize_phone(phone)
    code = code.strip() if isinstance(code, str) else ''
    if not phone:
        return False, '手机号或验证码不能为空'

    now = datetime.now()
    key = _reserve_login_attempt(tenant_id, phone, now)
    if not key:
        db.session.rollback()
        return False, SMS_LOCKED_MESSAGE

    row = (
        models.SmsCode.query.filter(
            models.SmsCode.tenant_id == tenant_id,
            models.SmsCode.phone == phone,
            models.SmsCode.scene == 'login',
        )
        .order_by(models.SmsCode.id.desc())
        .first()
    )
    valid_format = bool(re.fullmatch(r'[0-9]{6}', code))
    consumed = None
    if row and valid_format:
        consumed = db.session.execute(update(models.SmsCode).where(
            models.SmsCode.id == row.id,
            models.SmsCode.tenant_id == tenant_id,
            models.SmsCode.phone == phone,
            models.SmsCode.used == 0,
            models.SmsCode.expires_at > datetime.now(),
            models.SmsCode.code == code,
        ).values(used=1))
    if not consumed or consumed.rowcount != 1:
        db.session.commit()
        return False, '验证码错误或已失效，请重新获取'
    db.session.execute(update(models.LoginThrottle).where(
        models.LoginThrottle.scope == 'sms_account', models.LoginThrottle.key_hash == key,
    ).values(failed_count=0, first_failed_at=None, last_failed_at=None, locked_until=None))
    db.session.commit()
    return True, None
