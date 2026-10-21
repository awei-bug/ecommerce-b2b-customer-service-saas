from flask_restful import Resource, reqparse
from flask import request
from flask_shop import db

from flask_shop import models
from flask_shop.role import role_api, role_bp
from flask_shop.utils.token import login_required
from flask_shop.utils.tenant import get_for_tenant, require_tenant_id, tenant_filter


class Roles(Resource):
    method_decorators = [login_required]

    def get(self):
        try:
            from flask_shop.utils.rbac import staff_has_permission
            if not staff_has_permission('role:read'):
                return {'status': 403, 'msg': '无权限查看角色'}
            roles = tenant_filter(models.Role).all()
            role_list = [role.to_dict() for role in roles]
            return {'status': 200, 'msg': '获取角色列表成功', 'data': role_list}
        except Exception as e:
            print(e)
            return {'status': 500, 'msg': '获取角色列表失败'}

    def post(self):
        try:
            from flask_shop.utils.rbac import staff_has_permission
            if not staff_has_permission('role:write'):
                return {'status': 403, 'msg': '无权限管理角色'}
            body = request.get_json(silent=True) or {}
            name = body.get('name')
            desc = body.get('desc')
            if not name:
                return {'status': 400, 'msg': '角色名称不能为空'}
            tenant_id = require_tenant_id()
            exists = models.Role.query.filter(
                models.Role.tenant_id == tenant_id,
                models.Role.name == name,
            ).first()
            if exists:
                return {'status': 400, 'msg': '角色名称已存在'}
            role = models.Role(tenant_id=tenant_id, name=name, desc=desc)
            db.session.add(role)
            db.session.commit()
            return {'status': 200, 'msg': '添加角色成功', 'data': role.to_dict()}
        except Exception as e:
            print(e)
            return {'status': 500, 'msg': '添加角色失败'}


role_api.add_resource(Roles, '/roles/')


class Role(Resource):
    method_decorators = [login_required]

    def delete(self, id):
        try:
            from flask_shop.utils.rbac import staff_has_permission
            if not staff_has_permission('role:write'):
                return {'status': 403, 'msg': '无权限管理角色'}
            role = get_for_tenant(models.Role, id)
            if not role:
                return {'status': 404, 'msg': '角色不存在'}
            db.session.delete(role)
            db.session.commit()
            return {'status': 200, 'msg': '删除角色成功'}
        except Exception as e:
            print(e)
            return {'status': 500, 'msg': '删除角色失败'}

    def put(self, id):
        try:
            from flask_shop.utils.rbac import staff_has_permission, ALL_ACTION_CODES
            if not staff_has_permission('role:write'):
                return {'status': 403, 'msg': '无权限管理角色'}
            role = get_for_tenant(models.Role, id)
            if not role:
                return {'status': 404, 'msg': '角色不存在'}
            body = request.get_json(silent=True) or {}
            # 兼容 form / json
            parser = reqparse.RequestParser()
            parser.add_argument('name', type=str)
            parser.add_argument('desc', type=str)
            args = parser.parse_args()
            if args.get('name'):
                role.name = args.name
            if args.get('desc') is not None:
                role.desc = args.desc
            # 动作权限码
            if 'perm_codes' in body:
                codes = body.get('perm_codes') or []
                if not isinstance(codes, list):
                    return {'status': 400, 'msg': 'perm_codes 须为数组'}
                allowed = set(ALL_ACTION_CODES)
                clean = [str(c) for c in codes if str(c) in allowed]
                import json
                role.perm_codes = json.dumps(clean, ensure_ascii=False)
            db.session.commit()
            return {'status': 200, 'msg': '修改角色成功', 'data': role.to_dict()}
        except Exception as e:
            print(e)
            return {'status': 500, 'msg': '修改角色失败'}


role_api.add_resource(Role, '/role/<int:id>/')


@role_bp.route('/permissions/actions/', methods=['GET'])
@login_required
def list_action_codes():
    """返回全部可配置动作码（角色编辑页用）。"""
    from flask_shop.utils.rbac import ALL_ACTION_CODES, staff_has_permission
    if not staff_has_permission('role:read'):
        return {'status': 403, 'msg': '无权限'}
    labels = {
        'order:read': '订单-查看',
        'order:create': '订单-创建',
        'order:mark_paid': '订单-标记已付款',
        'order:ship': '订单-发货',
        'order:cancel': '订单-取消',
        'order:complete': '订单-完成',
        'order:refund': '订单-售后',
        'order:export': '订单-导出',
        'product:read': '商品-查看',
        'product:write': '商品-编辑',
        'category:write': '分类-编辑',
        'user:read': '员工-查看',
        'user:write': '员工-编辑',
        'role:read': '角色-查看',
        'role:write': '角色-编辑',
        'report:read': '数据-查看',
        'shop:settings': '店铺-设置',
        'service:read': '客服-查看会话',
        'service:reply': '客服-接待回复',
        'service:manage': '客服-管理优先级',
    }
    data = [{'code': c, 'label': labels.get(c, c)} for c in ALL_ACTION_CODES]
    return {'status': 200, 'msg': 'ok', 'data': data}


@role_bp.route('/role/<int:rid>/<int:mid>/')
@login_required
def del_menu(rid: int, mid: int):
    from flask_shop.utils.rbac import staff_has_permission
    if not staff_has_permission('role:write'):
        return {'status': 403, 'msg': '无权限分配菜单'}
    role = get_for_tenant(models.Role, rid)
    menu = db.session.get(models.Menu, mid)
    if all([role, menu]):
        if menu in role.menus:
            role.menus.remove(menu)
            if menu.level == 1:
                for temp in menu.children:
                    if temp in role.menus:
                        role.menus.remove(temp)
        db.session.commit()
        return {'status': 200, 'msg': '删除角色菜单成功'}
    return {'status': 500, 'msg': '角色或菜单不存在'}


@role_bp.route('/role/<int:rid>/', methods=['POST'])
@login_required
def set_menu(rid: int):
    try:
        from flask_shop.utils.rbac import staff_has_permission
        if not staff_has_permission('role:write'):
            return {'status': 403, 'msg': '无权限分配菜单'}
        role = get_for_tenant(models.Role, rid)
        if not role:
            return {'status': 404, 'msg': '角色不存在'}
        mids = (request.get_json(silent=True) or {}).get('mids')
        role.menus = []
        mids = (mids or '').split(',')
        for m in mids:
            if m:
                menu = db.session.get(models.Menu, int(m))
                if menu:
                    role.menus.append(menu)
        db.session.commit()
        return {'status': 200, 'msg': '分配权限成功'}
    except Exception as e:
        print(e)
        return {'status': 500, 'msg': '分配权限失败'}
