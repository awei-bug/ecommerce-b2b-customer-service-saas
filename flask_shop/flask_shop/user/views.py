import re

from flask import request
from flask_restful import Resource, reqparse

from flask_shop.user import user_bp, user_api
from flask_shop import models, db
from flask_shop.utils.token import generate_token, login_required
from flask_shop.utils.tenant import (
    get_for_tenant,
    load_tenant,
    require_tenant_id,
    resolve_tenant_identifiers,
    tenant_filter,
)
from flask_shop.utils.audit import write_audit


@user_bp.route('/')
def index():
    return 'Hello User!!'


@user_bp.route('/login/', methods=['POST'])
def login():
    """
    商户员工登录。
    必须指定租户：JSON 中 tenant_slug 或 tenant_id，或请求头 X-Tenant-Slug / X-Tenant-Id。
    """
    body = request.get_json(silent=True) or {}
    name = body.get('name')
    pwd = body.get('pwd')

    if not all([name, pwd]):
        return {'status': 400, 'msg': '参数不完整'}

    tenant_id, tenant_slug = resolve_tenant_identifiers()
    # body 里也可能直接带（resolve 已覆盖 json，这里兜底）
    if tenant_id is None:
        tenant_id = body.get('tenant_id')
    if not tenant_slug:
        tenant_slug = body.get('tenant_slug')

    tenant = load_tenant(tenant_id=tenant_id, tenant_slug=tenant_slug)
    if not tenant:
        return {'status': 400, 'msg': '租户不存在或已停用，请检查 tenant_slug / tenant_id'}

    user = models.User.query.filter(
        models.User.tenant_id == tenant.id,
        models.User.name == name,
    ).first()

    if not user or not user.check_password(pwd):
        write_audit(
            'staff.login_fail', 'user', None, f'name={name}',
            tenant_id=tenant.id, actor_type='staff', actor_id=None,
        )
        return {'status': 400, 'msg': '用户名或密码错误'}

    token = generate_token({
        'id': user.id,
        'staff_id': user.id,
        'tenant_id': tenant.id,
        'typ': 'merchant',
    })
    write_audit(
        'staff.login', 'user', user.id, f'name={name}',
        tenant_id=tenant.id, actor_type='staff', actor_id=user.id,
    )
    return {
        'status': 200,
        'msg': '登录成功',
        'data': {
            'token': token,
            'tenant': tenant.to_dict(),
            'user': user.to_dict(),
            'permissions': _staff_permission_payload(user),
        }
    }


def _staff_permission_payload(user):
    from flask_shop.utils.rbac import staff_permission_payload
    return staff_permission_payload(user)


class Users(Resource):
    method_decorators = [login_required]

    def get(self):
        from flask_shop.utils.rbac import staff_has_permission
        if not staff_has_permission('user:read'):
            return {'status': 403, 'msg': '无权限查看员工'}
        parser = reqparse.RequestParser()
        parser.add_argument('pnum', type=int, default=1, location='args')
        parser.add_argument('psize', type=int, default=2, location='args')
        parser.add_argument('name', type=str, location='args')
        args = parser.parse_args()

        name = args.get('name')
        pnum = args.get('pnum')
        psize = args.get('psize')

        query = tenant_filter(models.User)
        if name:
            query = query.filter(models.User.name.like(f'%{name}%'))
        user_list = query.paginate(page=pnum, per_page=psize)

        data = {
            'total': user_list.total,
            'pnum': pnum,
            'data': [u.to_dict() for u in user_list.items]
        }
        return {'status': 200, 'msg': '获取用户列表成功', 'data': data}

    def post(self):
        from flask_shop.utils.rbac import staff_has_permission
        if not staff_has_permission('user:write'):
            return {'status': 403, 'msg': '无权限管理员工'}
        body = request.get_json(silent=True) or {}
        name = body.get('name')
        pwd = body.get('pwd')
        real_pwd = body.get('real_pwd')

        if not all([name, pwd, real_pwd]):
            return {'status': 400, 'msg': '参数不完整'}
        if pwd != real_pwd:
            return {'status': 400, 'msg': '两次密码不一致'}
        if len(name) < 2:
            return {'status': 400, 'msg': '用户名不合法'}

        phone = body.get('phone')
        email = body.get('email')
        nick_name = body.get('nick_name')
        if phone and not re.match(r'^1[3456789]\d{9}$', phone):
            return {'status': 400, 'msg': '手机号不合法'}
        if email and not re.match(r'^[a-zA-Z0-9_-]+@[a-zA-Z0-9_-]+(\.[a-zA-Z0-9_-]+)+$', email):
            return {'status': 400, 'msg': '邮箱不合法'}

        tenant_id = require_tenant_id()
        role_id = body.get('role_id')

        exists = models.User.query.filter(
            models.User.tenant_id == tenant_id,
            models.User.name == name,
        ).first()
        if exists:
            return {'status': 400, 'msg': '用户名已存在'}

        if role_id:
            role = get_for_tenant(models.Role, role_id)
            if not role:
                return {'status': 400, 'msg': '角色不存在或不属于当前租户'}

        user = models.User(
            tenant_id=tenant_id,
            name=name,
            password=pwd,
            phone=phone,
            email=email,
            nick_name=nick_name,
            role_id=role_id if role_id else None,
        )
        db.session.add(user)
        db.session.commit()
        return {'status': 200, 'msg': '注册成功', 'data': user.to_dict()}


user_api.add_resource(Users, '/users/')


class User(Resource):
    method_decorators = [login_required]

    def get(self, id):
        from flask_shop.utils.rbac import staff_has_permission
        if not staff_has_permission('user:read'):
            return {'status': 403, 'msg': '无权限查看员工'}
        user = get_for_tenant(models.User, id)
        if user:
            return {'status': 200, 'msg': '查询成功', 'data': user.to_dict()}
        return {'status': 404, 'msg': '用户不存在'}

    def put(self, id):
        from flask_shop.utils.rbac import staff_has_permission
        if not staff_has_permission('user:write'):
            return {'status': 403, 'msg': '无权限管理员工'}
        user = get_for_tenant(models.User, id)
        if not user:
            return {'status': 404, 'msg': '用户不存在'}
        try:
            paser = reqparse.RequestParser()
            paser.add_argument('nick_name', type=str)
            paser.add_argument('phone', type=str)
            paser.add_argument('email', type=str)
            paser.add_argument('role_id', type=int)
            args = paser.parse_args()
            if args.get('nick_name'):
                user.nick_name = args.get('nick_name')
            if args.get('phone'):
                user.phone = args.get('phone')
            if args.get('email'):
                user.email = args.get('email')
            if args.get('role_id'):
                role = get_for_tenant(models.Role, args.get('role_id'))
                if not role:
                    return {'status': 400, 'msg': '角色不存在或不属于当前租户'}
                user.role_id = args.get('role_id')
            db.session.commit()
            return {'status': 200, 'msg': '修改成功', 'data': user.to_dict()}
        except Exception as e:
            print(e)
            return {'status': 400, 'msg': '修改失败'}

    def delete(self, id):
        try:
            from flask_shop.utils.rbac import staff_has_permission
            if not staff_has_permission('user:write'):
                return {'status': 403, 'msg': '无权限管理员工'}
            user = get_for_tenant(models.User, id)
            if not user:
                return {'status': 404, 'msg': '用户不存在'}
            db.session.delete(user)
            db.session.commit()
            return {'status': 200, 'msg': '删除成功'}
        except Exception as e:
            print(e)
            return {'status': 400, 'msg': '删除失败'}


user_api.add_resource(User, '/user/<int:id>/')


@user_bp.route('/reset_pwd/<int:id>/')
@login_required
def rest_pwd(id):
    try:
        from flask_shop.utils.rbac import staff_has_permission
        if not staff_has_permission('user:write'):
            return {'status': 403, 'msg': '无权限重置密码'}
        user = get_for_tenant(models.User, id)
        if not user:
            return {'status': 404, 'msg': '用户不存在'}
        user.password = '123456'
        db.session.commit()
        return {'status': 200, 'msg': '重置密码成功,密码为123456'}
    except Exception as e:
        print(e)
        return {'status': 400, 'msg': '重置密码失败'}


@user_bp.route('/shop/settings/', methods=['GET'])
@login_required
def get_shop_settings():
    """商户店铺设置（含付款指引）。"""
    from flask import g
    tenant = g.tenant
    if not tenant:
        return {'status': 400, 'msg': '租户上下文缺失'}
    return {'status': 200, 'msg': 'ok', 'data': tenant.to_dict()}


@user_bp.route('/shop/settings/', methods=['PUT', 'POST'])
@login_required
def update_shop_settings():
    """
    更新店铺展示信息与付款指引。
    body: { name?, pay_guide?, contact_phone?, logo?, status? }
    status: 1 营业中 / 0 暂停营业（C 端将无法下单）
    """
    from flask import g, request
    from flask_shop.utils.audit import write_audit
    tenant = g.tenant
    if not tenant:
        return {'status': 400, 'msg': '租户上下文缺失'}
    body = request.get_json(silent=True) or {}
    if 'name' in body and body.get('name'):
        tenant.name = str(body.get('name')).strip()[:64]
    if 'pay_guide' in body:
        tenant.pay_guide = (body.get('pay_guide') or '').strip() or None
    if 'contact_phone' in body:
        tenant.contact_phone = (body.get('contact_phone') or '').strip()[:32] or None
    if 'logo' in body:
        tenant.logo = (body.get('logo') or '').strip()[:255] or None
    if 'status' in body:
        st = body.get('status')
        if st in (0, 1, '0', '1', True, False):
            tenant.status = 1 if st in (1, '1', True) else 0
    db.session.commit()
    write_audit(
        'shop.settings_update',
        'tenant',
        tenant.id,
        f'name={tenant.name} status={tenant.status}',
    )
    return {'status': 200, 'msg': '保存成功', 'data': tenant.to_dict()}


@user_bp.route('/test/')
@login_required
def test_login_required():
    from flask import g
    return {
        'status': 200,
        'msg': '验证成功',
        'data': {
            'tenant_id': require_tenant_id(),
            'staff_id': g.staff_id,
        }
    }


@user_bp.route('/me/')
@login_required
def me():
    """当前登录员工与租户信息"""
    from flask import g
    user = get_for_tenant(models.User, g.staff_id)
    tenant = g.tenant
    if not user:
        return {'status': 404, 'msg': '用户不存在'}
    return {
        'status': 200,
        'msg': 'ok',
        'data': {
            'user': user.to_dict(),
            'tenant': tenant.to_dict() if tenant else None,
        }
    }
