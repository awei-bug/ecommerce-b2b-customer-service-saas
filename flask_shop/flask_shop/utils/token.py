"""JWT：B 端员工 + C 端买家。"""
import time
import uuid
from datetime import datetime, timezone
from functools import wraps

import jwt
from flask import current_app, g, request


def generate_token(data):
    payload = dict(data)
    payload['exp'] = time.time() + current_app.config['JWT_EXPIRATION_DELTA']
    # jti lets logout revoke this exact token; see is_token_revoked below.
    payload.setdefault('jti', uuid.uuid4().hex)
    payload.setdefault('typ', 'merchant')
    token = jwt.encode(payload, current_app.config['SECRET_KEY'], algorithm='HS256')
    if isinstance(token, bytes):
        token = token.decode('utf-8')
    return token


def generate_customer_token(customer_or_data):
    if hasattr(customer_or_data, 'id'):
        payload = {
            'id': customer_or_data.id,
            'customer_id': customer_or_data.id,
            'tenant_id': customer_or_data.tenant_id,
            'typ': 'customer',
        }
    else:
        payload = dict(customer_or_data)
        payload['typ'] = 'customer'
        if 'customer_id' not in payload and 'id' in payload:
            payload['customer_id'] = payload['id']
    payload['exp'] = time.time() + current_app.config['JWT_EXPIRATION_DELTA']
    token = jwt.encode(payload, current_app.config['SECRET_KEY'], algorithm='HS256')
    if isinstance(token, bytes):
        token = token.decode('utf-8')
    return token


def verify_token(token):
    if not token:
        return None
    try:
        payload = jwt.decode(token, current_app.config['SECRET_KEY'], algorithms=['HS256'])
    except Exception:
        return None
    if is_token_revoked(payload):
        return None
    return payload


def is_token_revoked(payload):
    """True when logout already withdrew this token.

    Only tokens carrying a `jti` can be revoked; legacy tokens without one keep
    working until they expire, which is why `generate_token` now always sets it.
    """
    jti = payload.get('jti')
    if not jti:
        return False
    try:
        from flask_shop import models
        row = models.RevokedToken.query.filter_by(jti=jti).first()
    except Exception:
        # A missing table must not lock everyone out; fail open here and let
        # the caller see an ordinary (valid) token.
        return False
    return row is not None


def revoke_token(payload):
    """Record a token as withdrawn. Idempotent; returns True when recorded."""
    jti = payload.get('jti')
    if not jti:
        return False
    from flask_shop import db, models
    if models.RevokedToken.query.filter_by(jti=jti).first():
        return True
    expires_at = datetime.fromtimestamp(
        float(payload.get('exp') or 0), tz=timezone.utc
    ).replace(tzinfo=None)
    db.session.add(
        models.RevokedToken(
            jti=jti,
            tenant_id=payload.get('tenant_id'),
            staff_id=payload.get('staff_id') or payload.get('id'),
            expires_at=expires_at,
        )
    )
    db.session.commit()
    return True


# 商家会话 cookie：云购（5000）是唯一签发点，其他端口（8080/8090/5174/5175）
# 依赖浏览器「同 host 不同端口共享 cookie」的行为读取同一份会话。
SESSION_COOKIE_NAME = 'dsh_merchant_session'


def _extract_token(allow_cookie=False):
    token = (
        request.headers.get('token')
        or request.headers.get('X-Customer-Token')
        or request.headers.get('Authorization', '')
    )
    if isinstance(token, str) and token.lower().startswith('bearer '):
        token = token[7:].strip()
    if not token and allow_cookie:
        # 显式请求头优先，缺头时才回落到会话 cookie
        token = (request.cookies.get(SESSION_COOKIE_NAME) or '').strip()
    return token


def session_cookie_max_age():
    """cookie 有效期与 token 有效期一致。"""
    return int(current_app.config['JWT_EXPIRATION_DELTA'])


def set_session_cookie(response, token):
    """写入商家会话 cookie。不设 Secure（本地 http 会被浏览器丢弃）、
    不设 Domain（让浏览器按 host 匹配，从而同 host 跨端口共享）。"""
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        max_age=session_cookie_max_age(),
        path='/',
        httponly=True,
        samesite='Lax',
    )
    return response


def clear_session_cookie(response):
    response.delete_cookie(
        SESSION_COOKIE_NAME, path='/', httponly=True, samesite='Lax',
    )
    return response


def authenticate_merchant(allow_cookie=True):
    """校验商家身份并绑定 g 上下文。

    成功返回 (None, None)；失败返回 (响应体, HTTP 状态)。
    供 login_required（保持历史「HTTP 200 + body.status」语义）与
    /user/session/（需要真正的 HTTP 401）共用同一份校验逻辑。
    """
    payload = verify_token(_extract_token(allow_cookie))
    if not payload:
        return {'status': 401, 'msg': 'token 无效或已过期'}, 401
    if payload.get('typ') and payload.get('typ') != 'merchant':
        return {'status': 401, 'msg': '请使用商家账号登录'}, 401

    tenant_id = payload.get('tenant_id')
    staff_id = payload.get('staff_id') or payload.get('id')
    if not tenant_id or not staff_id:
        return {'status': 401, 'msg': 'token 缺少租户或用户信息，请重新登录'}, 401

    # 请求头若带租户，必须与 JWT 一致（防串租户）
    header_tid = request.headers.get('X-Tenant-Id')
    if header_tid not in (None, ''):
        try:
            header_tid_int = int(str(header_tid).strip())
        except (TypeError, ValueError):
            return {'status': 400, 'msg': 'X-Tenant-Id 无效'}, 400
        if int(header_tid_int) != int(tenant_id):
            return {'status': 403, 'msg': '租户与登录身份不一致'}, 403

    from flask_shop import models
    tenant = models.Tenant.query.filter_by(id=tenant_id).first()
    if not tenant:
        return {'status': 401, 'msg': '租户不存在'}, 401

    # 先绑租户上下文再查 User：User 带 tenant_id，
    # TENANT_STRICT 下未绑租户查询会被隔离层拦截
    g.tenant = tenant
    g.tenant_id = tenant.id

    user = models.User.query.filter_by(id=staff_id, tenant_id=tenant.id).first()
    if not user:
        return {'status': 401, 'msg': '员工不存在'}, 401

    g.staff_id = staff_id
    g.user_id = staff_id
    g.staff = user
    g.token_payload = payload
    return None, None


def login_required(view_func):
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        # allow_cookie：登录态由云购统一签发，其他端口靠 cookie 复用同一会话
        error, _status = authenticate_merchant(allow_cookie=True)
        if error:
            return error
        return view_func(*args, **kwargs)

    return wrapper


def customer_login_required(view_func):
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        payload = verify_token(_extract_token())
        if not payload:
            return {'status': 401, 'msg': '请先登录'}
        if payload.get('typ') != 'customer':
            return {'status': 401, 'msg': '请使用买家账号登录'}

        tenant_id = payload.get('tenant_id') or getattr(g, 'tenant_id', None)
        customer_id = payload.get('customer_id') or payload.get('id')
        if not tenant_id or not customer_id:
            return {'status': 401, 'msg': 'token 无效'}

        from flask_shop import db, models
        # 先绑租户上下文再查 Customer（Customer 带 tenant_id，STRICT 下顺序不能反）
        if not getattr(g, 'tenant', None):
            tenant = db.session.get(models.Tenant, tenant_id)
            g.tenant = tenant
        g.tenant_id = tenant_id

        customer = models.Customer.query.filter_by(
            id=customer_id, tenant_id=tenant_id
        ).first()
        if not customer or customer.status != 1:
            return {'status': 401, 'msg': '买家不存在或已禁用'}

        g.customer = customer
        g.customer_id = customer.id
        g.token_payload = payload
        return view_func(*args, **kwargs)

    return wrapper