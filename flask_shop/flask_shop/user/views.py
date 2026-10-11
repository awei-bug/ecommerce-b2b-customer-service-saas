# -*- coding: utf-8 -*-
"""B 端账号、登录、店铺设置。"""
import secrets
import string

from flask_shop.utils.rate_limit import rate_limit
from flask import current_app, g, request
from flask_restful import Resource, reqparse

from flask_shop import db, models
from flask_shop.user import user_api, user_bp
from flask_shop.utils.audit import write_audit
from flask_shop.utils.tenant import get_for_tenant, require_tenant_id, tenant_filter
from flask_shop.utils.token import generate_token, login_required
from flask_shop.utils.auth_security import (
    clear_login_failures,
    login_lock_status,
    record_login_failure,
)


DEFAULT_PAY_GUIDE = (
    '下单后请按本店说明完成付款（微信/支付宝转账等）。\n'
    '付款时备注订单号，商家确认到账后会将订单更新为「已付款」并安排发货。\n'
    '本系统当前支持模拟支付（开发演示）与人工确认收款。'
)


@user_bp.route('/login/', methods=['POST'])
@rate_limit(max_calls=20, per_seconds=60, prefix="login")
def login():
    body = request.get_json(silent=True) or {}
    name = (body.get('name') or '').strip()
    pwd = body.get('pwd') or ''
    tenant_slug = (body.get('tenant_slug') or '').strip()

    if not name or not pwd:
        return {'status': 400, 'msg': '请输入账号和密码'}

    locked_seconds = login_lock_status(name, tenant_slug)
    if locked_seconds:
        return {
            'status': 429,
            'msg': f'登录失败次数过多，请 {max(1, (locked_seconds + 59) // 60)} 分钟后再试',
        }, 429

    q = models.Tenant.query
    if tenant_slug:
        tenant = q.filter_by(slug=tenant_slug).first()
    else:
        tenant = q.order_by(models.Tenant.id.asc()).first()
    if not tenant:
        return {'status': 400, 'msg': '店铺不存在，请先执行 seed 初始化'}

    # 解析出默认租户后再次检查账户锁，避免省略 tenant_slug 绕过账户维度锁定。
    locked_seconds = login_lock_status(name, tenant.slug)
    if locked_seconds:
        return {
            'status': 429,
            'msg': f'登录失败次数过多，请 {max(1, (locked_seconds + 59) // 60)} 分钟后再试',
        }, 429

    user = models.User.query.filter_by(tenant_id=tenant.id, name=name).first()
    if not user or not user.check_password(pwd):
        locked_seconds = record_login_failure(name, tenant_slug or tenant.slug)
        if locked_seconds:
            return {
                'status': 429,
                'msg': f'登录失败次数过多，请 {max(1, (locked_seconds + 59) // 60)} 分钟后再试',
            }, 429
        return {'status': 400, 'msg': '用户名或密码错误'}

    clear_login_failures(name, tenant_slug or tenant.slug)

    token = generate_token({
        'id': user.id,
        'staff_id': user.id,
        'tenant_id': tenant.id,
        'typ': 'merchant',
    })
    # 弱口令提示（不返回哈希；仅布尔）
    password_is_default = False
    try:
        password_is_default = bool(user.check_password('123456'))
    except Exception:
        password_is_default = False

    security_tips = []
    if password_is_default:
        security_tips.append('当前仍为默认密码 123456，请尽快到「店铺设置」修改')
    if getattr(tenant, 'data_mode', None) == 'demo':
        security_tips.append('当前店铺为演示数据模式，订单、业绩和顾客数据不能作为真实经营结果')
    if current_app.config.get('DEBUG'):
        security_tips.append('当前服务开启开发模式，正式对外前必须切换到 product 配置')
    if current_app.config.get('ALLOW_MOCK_PAY'):
        security_tips.append('当前允许模拟支付，仅限本地演示，正式环境必须关闭')
    if current_app.config.get('SMS_DEV_MODE'):
        security_tips.append('当前启用固定/开发验证码，仅限本地演示，正式环境必须关闭')

    return {
        'status': 200,
        'msg': '登录成功',
        'data': {
            'token': token,
            'tenant': tenant.to_dict(),
            'user': user.to_dict(),
            'password_is_default': password_is_default,
            'security_tips': security_tips,
        },
    }


class Me(Resource):
    method_decorators = [login_required]

    def get(self):
        return {
            'status': 200,
            'msg': 'ok',
            'data': {
                'user': g.staff.to_dict(),
                'tenant': g.tenant.to_dict(),
            },
        }


user_api.add_resource(Me, '/me/')


class Users(Resource):
    method_decorators = [login_required]

    def get(self):
        from flask_shop.utils.rbac import staff_has_permission
        if not staff_has_permission('user:read'):
            return {'status': 403, 'msg': '无权限查看员工'}
        parser = reqparse.RequestParser()
        parser.add_argument('pagenum', type=int, location='args', default=1)
        parser.add_argument('pagesize', type=int, location='args', default=10)
        parser.add_argument('pageNum', type=int, location='args')
        parser.add_argument('pageSize', type=int, location='args')
        parser.add_argument('name', type=str, location='args')
        args = parser.parse_args()
        page = args.get('pageNum') or args.get('pagenum') or 1
        size = args.get('pageSize') or args.get('pagesize') or 10
        query = tenant_filter(models.User)
        if args.get('name'):
            query = query.filter(models.User.name.like(f"%{args['name']}%"))
        total = query.count()
        rows = query.order_by(models.User.id.desc()).offset((page - 1) * size).limit(size).all()
        return {
            'status': 200,
            'msg': 'ok',
            'data': [u.to_dict() for u in rows],
            'total': total,
            'pagenum': page,
            'pagesize': size,
        }

    def post(self):
        from flask_shop.utils.rbac import staff_has_permission
        if not staff_has_permission('user:write'):
            return {'status': 403, 'msg': '无权限管理员工'}
        body = request.get_json(silent=True) or {}
        name = (body.get('name') or '').strip()
        pwd = body.get('pwd') or body.get('password') or ''
        if not name or not pwd:
            return {'status': 400, 'msg': '用户名和密码必填'}
        tenant_id = require_tenant_id()
        if models.User.query.filter_by(tenant_id=tenant_id, name=name).first():
            return {'status': 400, 'msg': '用户名已存在'}
        role_id = body.get('role_id') or body.get('rold_id')
        user = models.User(
            tenant_id=tenant_id,
            name=name,
            nick_name=body.get('nick_name') or name,
            phone=body.get('phone'),
            email=body.get('email'),
            role_id=role_id,
        )
        user.password = pwd
        db.session.add(user)
        db.session.commit()
        write_audit('user.create', 'user', user.id, name)
        return {'status': 200, 'msg': '添加成功', 'data': user.to_dict()}


user_api.add_resource(Users, '/users/')


class UserDetail(Resource):
    method_decorators = [login_required]

    def get(self, id):
        from flask_shop.utils.rbac import staff_has_permission
        if not staff_has_permission('user:read'):
            return {'status': 403, 'msg': '无权限'}
        user = get_for_tenant(models.User, id)
        if not user:
            return {'status': 404, 'msg': '用户不存在'}
        return {'status': 200, 'msg': 'ok', 'data': user.to_dict()}

    def put(self, id):
        from flask_shop.utils.rbac import staff_has_permission
        if not staff_has_permission('user:write'):
            return {'status': 403, 'msg': '无权限'}
        user = get_for_tenant(models.User, id)
        if not user:
            return {'status': 404, 'msg': '用户不存在'}
        body = request.get_json(silent=True) or {}
        for key in ('nick_name', 'phone', 'email'):
            if key in body:
                setattr(user, key, body.get(key))
        if 'role_id' in body or 'rold_id' in body:
            user.role_id = body.get('role_id') or body.get('rold_id')
        if body.get('name'):
            user.name = body.get('name').strip()
        db.session.commit()
        write_audit('user.update', 'user', user.id)
        return {'status': 200, 'msg': '修改成功', 'data': user.to_dict()}

    def delete(self, id):
        from flask_shop.utils.rbac import staff_has_permission
        if not staff_has_permission('user:write'):
            return {'status': 403, 'msg': '无权限'}
        user = get_for_tenant(models.User, id)
        if not user:
            return {'status': 404, 'msg': '用户不存在'}
        if user.id == g.staff_id:
            return {'status': 400, 'msg': '不能删除当前登录账号'}
        db.session.delete(user)
        db.session.commit()
        write_audit('user.delete', 'user', id)
        return {'status': 200, 'msg': '已删除'}


user_api.add_resource(UserDetail, '/user/<int:id>/')


@user_bp.route('/user/<int:id>/reset_pwd/', methods=['POST'])
@login_required
def reset_user_password(id):
    from flask_shop.utils.rbac import staff_has_permission
    if not staff_has_permission('user:write'):
        return {'status': 403, 'msg': '无权限'}
    user = get_for_tenant(models.User, id)
    if not user:
        return {'status': 404, 'msg': '用户不存在'}
    alphabet = string.ascii_letters + string.digits
    temp = ''.join(secrets.choice(alphabet) for _ in range(8))
    user.password = temp
    db.session.commit()
    write_audit('user.reset_pwd', 'user', id)
    return {'status': 200, 'msg': '已重置', 'data': {'temp_password': temp}}




@user_bp.route('/change-password/', methods=['POST'])
@login_required
def change_password():
    """店长/员工修改自己的登录密码。body: { old_pwd, new_pwd }"""
    body = request.get_json(silent=True) or {}
    old_pwd = body.get('old_pwd') or body.get('old_password') or ''
    new_pwd = body.get('new_pwd') or body.get('new_password') or ''
    if not old_pwd or not new_pwd:
        return {'status': 400, 'msg': '请填写原密码和新密码'}
    if len(str(new_pwd)) < 6:
        return {'status': 400, 'msg': '新密码至少 6 位'}
    if str(new_pwd) == '123456':
        return {'status': 400, 'msg': '新密码不能为 123456'}
    user = getattr(g, 'staff', None)
    if not user or not user.check_password(old_pwd):
        return {'status': 400, 'msg': '原密码不正确'}
    user.password = str(new_pwd)
    db.session.commit()
    try:
        from flask_shop.utils.audit import write_audit
        write_audit('user.change_password', 'user', user.id, 'self')
    except Exception:
        pass
    return {'status': 200, 'msg': '密码已修改，请使用新密码登录'}


@user_bp.route('/shop/settings/', methods=['GET'])
@login_required
def get_shop_settings():
    from flask_shop.utils.rbac import staff_has_permission
    if not (
        staff_has_permission('shop:settings')
        or staff_has_permission('product:write')
        or getattr(g.staff, 'is_admin', 0)
    ):
        # 超管角色放行
        from flask_shop.utils.rbac import get_staff_role, _is_super_role
        role = get_staff_role(g.staff_id, g.tenant_id)
        if not _is_super_role(role):
            return {'status': 403, 'msg': '无权限'}
    t = g.tenant
    data = t.to_dict()
    if not data.get('pay_guide'):
        data['pay_guide'] = DEFAULT_PAY_GUIDE
    data.setdefault('payment_mode', 'manual_qr')
    data['pay_qr_wechat'] = getattr(t, 'pay_qr_wechat', None)
    data['pay_qr_alipay'] = getattr(t, 'pay_qr_alipay', None)
    return {'status': 200, 'msg': 'ok', 'data': data}


@user_bp.route('/shop/settings/', methods=['PUT', 'POST'])
@login_required
def update_shop_settings():
    from flask_shop.utils.rbac import staff_has_permission, get_staff_role, _is_super_role
    role = get_staff_role(g.staff_id, g.tenant_id)
    if not (
        staff_has_permission('shop:settings')
        or _is_super_role(role)
    ):
        return {'status': 403, 'msg': '无权限修改店铺设置'}
    body = request.get_json(silent=True) or {}
    t = g.tenant
    if 'name' in body and body.get('name'):
        t.name = str(body.get('name')).strip()[:64]
    if 'contact_phone' in body:
        t.contact_phone = (body.get('contact_phone') or '')[:32] or None
    if 'pay_guide' in body:
        t.pay_guide = body.get('pay_guide')
    if 'theme' in body:
        theme = str(body.get('theme') or 'retail').strip().lower()
        if theme not in ('retail', 'tea', 'fashion', 'digital'):
            return {'status': 400, 'msg': 'theme 仅支持 retail/tea/fashion/digital'}
        t.theme = theme
    if 'status' in body:
        try:
            t.status = int(body.get('status'))
        except (TypeError, ValueError):
            return {'status': 400, 'msg': 'status 不合法'}
    if 'logo' in body:
        t.logo = (body.get('logo') or '')[:255] or None
    if 'pay_qr_wechat' in body:
        t.pay_qr_wechat = (body.get('pay_qr_wechat') or '')[:255] or None
    if 'pay_qr_alipay' in body:
        t.pay_qr_alipay = (body.get('pay_qr_alipay') or '')[:255] or None
    db.session.commit()
    write_audit('shop.settings', 'tenant', t.id)
    return {'status': 200, 'msg': '已保存', 'data': t.to_dict()}
