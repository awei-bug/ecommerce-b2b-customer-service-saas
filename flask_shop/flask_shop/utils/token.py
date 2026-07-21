'''
JWT 工具

商户员工载荷 typ=merchant：
  id / staff_id, tenant_id

C 端买家载荷 typ=customer：
  customer_id, tenant_id, phone
'''
import time
from functools import wraps

import jwt
from flask import current_app, g, request

from flask_shop.utils.tenant import bind_tenant, load_tenant, resolve_tenant_identifiers


def generate_token(data):
    payload = dict(data)
    payload['exp'] = time.time() + current_app.config['JWT_EXPIRATION_DELTA']
    payload.setdefault('typ', 'merchant')
    token = jwt.encode(payload, current_app.config['SECRET_KEY'], algorithm='HS256')
    if isinstance(token, bytes):
        token = token.decode('utf-8')
    return token


def generate_customer_token(customer):
    return generate_token({
        'typ': 'customer',
        'customer_id': customer.id,
        'tenant_id': customer.tenant_id,
        'phone': customer.phone,
    })


def verify_token(token):
    if not token:
        return None
    try:
        data = jwt.decode(token, current_app.config['SECRET_KEY'], algorithms=['HS256'])
    except Exception:
        return None
    return data


def _extract_token():
    token = request.headers.get('token') or request.headers.get('Authorization', '')
    if isinstance(token, str) and token.lower().startswith('bearer '):
        token = token[7:].strip()
    # C 端也可用专用头，避免与商户后台混用时误传
    if not token:
        token = request.headers.get('X-Customer-Token', '')
    return token


def login_required(view_func):
    """商户 JWT：写入 g.tenant_id / g.staff_id。"""
    @wraps(view_func)
    def verify_token_info(*args, **kwargs):
        payload = verify_token(_extract_token())
        if not payload:
            return {'status': 401, 'msg': 'token 无效或已过期'}
        if payload.get('typ') and payload.get('typ') != 'merchant':
            return {'status': 401, 'msg': '请使用商户账号登录'}

        tenant_id = payload.get('tenant_id')
        staff_id = payload.get('staff_id') or payload.get('id')
        if not tenant_id or not staff_id:
            return {'status': 401, 'msg': 'token 缺少租户或用户信息，请重新登录'}

        header_tid, header_slug = resolve_tenant_identifiers()
        if header_tid is not None and int(header_tid) != int(tenant_id):
            return {'status': 403, 'msg': '请求租户与登录租户不一致'}
        if header_slug:
            tenant = load_tenant(tenant_id=tenant_id)
            if not tenant or tenant.slug != header_slug:
                return {'status': 403, 'msg': '请求租户与登录租户不一致'}

        tenant = load_tenant(tenant_id=tenant_id)
        if not tenant:
            return {'status': 401, 'msg': '租户不存在或已停用'}

        # 提前绑定租户上下文：下方对 User（带 tenant_id）的查询需在租户作用域内执行，
        # 否则在 TENANT_STRICT 模式下会因 g.tenant_id 未绑定而报错。
        bind_tenant(tenant)

        from flask_shop import models
        user = models.User.query.filter_by(id=staff_id, tenant_id=tenant.id).first()
        if not user:
            return {'status': 401, 'msg': '员工不存在'}

        g.staff_id = staff_id
        g.user_id = staff_id
        g.staff = user
        g.staff_role = user.role
        g.customer_id = None
        g.token_payload = payload
        return view_func(*args, **kwargs)

    return verify_token_info


def customer_login_required(view_func):
    """C 端买家 JWT：写入 g.customer_id / g.tenant_id。"""
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        payload = verify_token(_extract_token())
        if not payload or payload.get('typ') != 'customer':
            return {'status': 401, 'msg': '请先登录（买家）'}

        tenant_id = payload.get('tenant_id')
        customer_id = payload.get('customer_id')
        if not tenant_id or not customer_id:
            return {'status': 401, 'msg': 'token 无效，请重新登录'}

        # 请求租户须与 token 一致
        header_tid, header_slug = resolve_tenant_identifiers()
        if header_tid is not None and int(header_tid) != int(tenant_id):
            return {'status': 403, 'msg': '请求租户与登录租户不一致'}

        tenant = load_tenant(tenant_id=tenant_id)
        if not tenant:
            return {'status': 401, 'msg': '租户不存在或已停用'}
        if header_slug and tenant.slug != header_slug:
            return {'status': 403, 'msg': '请求租户与登录租户不一致'}

        # 提前绑定：下方对 Customer（带 tenant_id）的查询需在租户作用域内执行
        bind_tenant(tenant)

        from flask_shop import models
        customer = models.Customer.query.filter_by(
            id=customer_id, tenant_id=tenant_id, status=1
        ).first()
        if not customer:
            return {'status': 401, 'msg': '买家不存在或已禁用'}

        g.customer = customer
        g.customer_id = customer.id
        g.staff_id = None
        g.token_payload = payload
        return view_func(*args, **kwargs)

    return wrapper


def optional_customer_login(view_func):
    """可选买家登录：有合法 customer token 则绑定。"""
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        payload = verify_token(_extract_token())
        g.customer = None
        g.customer_id = None
        if payload and payload.get('typ') == 'customer':
            tenant = load_tenant(tenant_id=payload.get('tenant_id'))
            if tenant:
                # 提前绑定：下方对 Customer（带 tenant_id）的查询需在租户作用域内执行
                bind_tenant(tenant)
                from flask_shop import models
                customer = models.Customer.query.filter_by(
                    id=payload.get('customer_id'),
                    tenant_id=tenant.id,
                    status=1,
                ).first()
                if customer:
                    g.customer = customer
                    g.customer_id = customer.id
                    g.token_payload = payload
        return view_func(*args, **kwargs)
    return wrapper


def optional_login(view_func):
    """可选商户登录。"""
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        payload = verify_token(_extract_token())
        if payload and payload.get('tenant_id') and payload.get('typ', 'merchant') == 'merchant':
            tenant = load_tenant(tenant_id=payload['tenant_id'])
            if tenant:
                bind_tenant(tenant)
                g.staff_id = payload.get('staff_id') or payload.get('id')
                g.user_id = g.staff_id
                g.token_payload = payload
        return view_func(*args, **kwargs)
    return wrapper
