"""
C 端短信验证码（骨架）

开发默认：
  SMS_DEV_MODE=1 时不发真短信，验证码固定为 SMS_DEV_CODE（默认 123456），
  并在发送接口返回 dev_code 方便联调。

生产：接阿里云/腾讯云后，在 send_login_code 内替换发送逻辑，并关闭 DEV_MODE。
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


def dev_code():
    return str(current_app.config.get('SMS_DEV_CODE') or '123456')


def send_login_code(tenant_id, phone):
    """
    生成并保存验证码。返回 (code_for_response_or_None, error_msg)
    开发模式返回 code 便于联调；生产返回 None（不把验证码回给前端）。
    """
    phone = normalize_phone(phone)
    if not phone:
        return None, '手机号不合法'

    # 简单频控：60 秒内同一租户+手机不重复发
    since = datetime.now() - timedelta(seconds=60)
    recent = models.SmsCode.query.filter(
        models.SmsCode.tenant_id == tenant_id,
        models.SmsCode.phone == phone,
        models.SmsCode.scene == 'login',
        models.SmsCode.create_time >= since,
    ).order_by(models.SmsCode.id.desc()).first()
    if recent and not recent.used:
        return None, '发送过于频繁，请稍后再试'

    if is_dev_mode():
        code = dev_code()
    else:
        code = f'{random.randint(0, 999999):06d}'
        # TODO: 调用短信供应商 API 发送 code
        # raise NotImplementedError if provider not configured

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

    if is_dev_mode():
        return code, None
    return None, None


def verify_login_code(tenant_id, phone, code):
    """校验成功返回 True，并标记 used。"""
    phone = normalize_phone(phone)
    code = (code or '').strip()
    if not phone or not code:
        return False, '手机号或验证码不能为空'

    # 开发模式允许直接用固定码（即使未点发送）
    if is_dev_mode() and code == dev_code():
        return True, None

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
        return False, '验证码错误'
    if row.expires_at < datetime.now():
        return False, '验证码已过期'
    row.used = 1
    db.session.commit()
    return True, None
