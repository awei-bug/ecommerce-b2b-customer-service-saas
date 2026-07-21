from flask_restful import Resource, reqparse
from flask import request
from sqlalchemy import text

from flask_shop import models
from flask_shop import db
from flask_shop.category import cate_api, attr_api, cate_bp
from flask_shop.utils.token import login_required
from flask_shop.utils.tenant import get_for_tenant, require_tenant_id, tenant_filter


class Categorys(Resource):
    method_decorators = [login_required]

    def get(self):
        from flask_shop.utils.rbac import staff_has_permission
        if not staff_has_permission('product:read'):
            return {'status': 403, 'msg': '无权限查看分类'}
        level = request.args.get('level')
        pnum = request.args.get('pnum')
        psize = request.args.get('psize')
        level = int(level) if level else 3

        base_query = tenant_filter(models.Category).filter(models.Category.level == 1)
        if all([pnum, psize]):
            cates = base_query.paginate(page=int(pnum), per_page=int(psize))
            items = cates.items
        else:
            items = base_query.all()
        cate_list = self.to_tree(items, level)
        return {'status': 200, 'msg': '获取分类成功', 'data': cate_list}

    def to_tree(self, info: list, level):
        info_list = []
        for i in info:
            # 子分类也限制在同租户（relationship 本身挂在同一树上，创建时已写 tenant_id）
            i_dict = i.to_dict()
            if i.level < level:
                i_dict['children'] = self.to_tree(i.children, level)
            info_list.append(i_dict)
        return info_list

    def post(self):
        try:
            from flask_shop.utils.rbac import staff_has_permission
            if not staff_has_permission('category:write'):
                return {'status': 403, 'msg': '无权限管理分类'}
            parser = reqparse.RequestParser()
            parser.add_argument('name', type=str, required=True)
            parser.add_argument('level', type=int, required=True)
            parser.add_argument('pid', type=int)
            args = parser.parse_args()
            tenant_id = require_tenant_id()
            if args.get('pid'):
                parent = get_for_tenant(models.Category, args.get('pid'))
                if not parent:
                    return {'status': 400, 'msg': '父分类不存在'}
                c = models.Category(
                    tenant_id=tenant_id,
                    name=args.get('name'),
                    level=args.get('level'),
                    pid=args.get('pid'),
                )
            else:
                c = models.Category(
                    tenant_id=tenant_id,
                    name=args.get('name'),
                    level=args.get('level'),
                )
            db.session.add(c)
            db.session.commit()
            return {'status': 200, 'msg': '添加分类成功', 'data': c.to_dict()}
        except Exception as e:
            print(e)
            return {'status': 500, 'msg': '添加分类失败'}


cate_api.add_resource(Categorys, '/categorys/')


class Attributes(Resource):
    method_decorators = [login_required]

    def get(self):
        parser = reqparse.RequestParser()
        parser.add_argument('cid', type=int, required=True, location='args')
        parser.add_argument('_type', type=str, required=True, location='args')
        args = parser.parse_args()

        cate = get_for_tenant(models.Category, args.get('cid'))
        if not cate:
            return {'status': 404, 'msg': '分类不存在'}

        attr_list = []
        if args.get('_type') == 'static':
            attr_list = [a.to_dict() for a in cate.attrs if a._type == 'static']
        elif args.get('_type') == 'dynamic':
            attr_list = [a.to_dict() for a in cate.attrs if a._type == 'dynamic']
        return {'status': 200, 'msg': '获取属性成功', 'data': attr_list}

    def post(self):
        try:
            parser = reqparse.RequestParser()
            parser.add_argument('name', type=str, required=True)
            parser.add_argument('val', type=str)
            parser.add_argument('_type', type=str, required=True)
            parser.add_argument('cid', type=int, required=True)
            args = parser.parse_args()

            cate = get_for_tenant(models.Category, args.get('cid'))
            if not cate:
                return {'status': 404, 'msg': '分类不存在'}

            tenant_id = require_tenant_id()
            c = models.Attribute(
                tenant_id=tenant_id,
                name=args.get('name'),
                val=args.get('val'),
                _type=args.get('_type'),
                cid=args.get('cid'),
            )
            db.session.add(c)
            db.session.commit()
            return {'status': 200, 'msg': '添加属性成功', 'data': c.to_dict()}
        except Exception as e:
            print(e)
            return {'status': 500, 'msg': '添加属性失败'}


attr_api.add_resource(Attributes, '/attributes/')


class Attribute(Resource):
    method_decorators = [login_required]

    def get(self, id):
        attr = get_for_tenant(models.Attribute, id)
        if not attr:
            return {'status': 404, 'msg': '属性不存在'}
        return {'status': 200, 'msg': '获取属性成功', 'data': attr.to_dict()}

    def put(self, id):
        try:
            attr = get_for_tenant(models.Attribute, id)
            if not attr:
                return {'status': 404, 'msg': '属性不存在'}
            parser = reqparse.RequestParser()
            parser.add_argument('name', type=str)
            parser.add_argument('val', type=str)
            parser.add_argument('_type', type=str)
            parser.add_argument('cid', type=int)
            args = parser.parse_args()
            if args.get('name'):
                attr.name = args.get('name')
            if args.get('val'):
                attr.val = args.get('val')
            if args.get('_type'):
                attr._type = args.get('_type')
            if args.get('cid'):
                cate = get_for_tenant(models.Category, args.get('cid'))
                if not cate:
                    return {'status': 400, 'msg': '分类不存在'}
                attr.cid = args.get('cid')
            db.session.commit()
            return {'status': 200, 'msg': '修改属性成功'}
        except Exception as e:
            print(e)
            return {'status': 500, 'msg': '修改属性失败'}

    def delete(self, id):
        try:
            attr = get_for_tenant(models.Attribute, id)
            if not attr:
                return {'status': 404, 'msg': '属性不存在'}
            db.session.delete(attr)
            db.session.commit()
            return {'status': 200, 'msg': '删除属性成功'}
        except Exception as e:
            print(e)
            return {'status': 500, 'msg': '删除属性失败'}


attr_api.add_resource(Attribute, '/attribute/<int:id>/')


@cate_bp.route('/cate_grup/')
@login_required
def cate_grup():
    tenant_id = require_tenant_id()
    sql = text(
        'select level, count(1) from t_category where tenant_id = :tid group by level'
    )
    rs = db.session.execute(sql, {'tid': tenant_id}).all()
    data = {
        'name': '分类数量',
        'xAxis': [f'{r[0]}级分类' for r in rs],
        'series': [r[1] for r in rs]
    }
    return {'status': 200, 'msg': '获取数据成功', 'data': data}
