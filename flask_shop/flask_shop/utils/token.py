"""JWT：B 端员工 + C 端买家。"""
import time
from functools import wraps

import jwt
from flask import current_app, g, request


def generate_token(data):
    payload = dict(data)
    payload['exp'] = time.time() + current_app.config['JWT_EXPIRATION_DELTA']
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
        return jwt.decode(token, current_app.config['SECRET_KEY'], algorithms=['HS256'])
    except Exception:
        return None


def _extract_token():
    token = (
        request.headers.get('token')
        or request.headers.get('X-Customer-Token')
        or request.headers.get('Authorization', '')
    )
    if isinstance(token, str) and token.lower().startswith('bearer '):
        token = token[7:].strip()
    return token


def login_required(view_func):
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        payload = verify_token(_extract_token())
        if not payload:
            return {'status': 401, 'msg': 'token 无效或已过期'}
        if payload.get('typ') and payload.get('typ') != 'merchant':
            return {'status': 401, 'msg': '请使用商家账号登录'}

        tenant_id = payload.get('tenant_id')
        staff_id = payload.get('staff_id') or payload.get('id')
        if not tenant_id or not staff_id:
            return {'status': 401, 'msg': 'token 缺少租户或用户信息，请重新登录'}

        # 请求头若带租户，必须与 JWT 一致（防串租户）
        header_tid = request.headers.get('X-Tenant-Id')
        if header_tid not in (None, ''):
            try:
                header_tid_int = int(str(header_tid).strip())
            except (TypeError, ValueError):
                return {'status': 400, 'msg': 'X-Tenant-Id 无效'}
            if int(header_tid_int) != int(tenant_id):
                return {'status': 403, 'msg': '租户与登录身份不一致'}

        from flask_shop import models
        tenant = models.Tenant.query.filter_by(id=tenant_id).first()
        if not tenant:
            return {'status': 401, 'msg': '租户不存在'}

        # 先绑租户上下文再查 User：User 带 tenant_id，
        # TENANT_STRICT 下未绑租户查询会被隔离层拦截
        g.tenant = tenant
        g.tenant_id = tenant.id

        user = models.User.query.filter_by(id=staff_id, tenant_id=tenant.id).first()
        if not user:
            return {'status': 401, 'msg': '员工不存在'}

        g.staff_id = staff_id
        g.user_id = staff_id
        g.staff = user
        g.token_payload = payload
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

        from flask_shop import models
        # 先绑租户上下文再查 Customer（Customer 带 tenant_id，STRICT 下顺序不能反）
        if not getattr(g, 'tenant', None):
            tenant = models.Tenant.query.get(tenant_id)
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