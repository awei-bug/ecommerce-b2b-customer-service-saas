from flask import request
from flask_restful import Resource

from flask_shop.menu import menu_api
from flask_shop import models
from flask_shop.utils.token import login_required


class Menus(Resource):
    method_decorators = [login_required]

    def get(self):
        type_ = request.args.get('type_')
        if type_ == 'tree':
            menu_list = models.Menu.query.filter(models.Menu.level == 1).all()
            menu_data = [m.to_dict_tree() for m in menu_list]
            return {'status': 200, 'msg': '获取菜单成功', 'data': menu_data}
        menu_list = models.Menu.query.filter(models.Menu.level != 0).all()
        menu_data = [m.to_dict_list() for m in menu_list]
        return {'status': 200, 'msg': '获取菜单成功', 'data': menu_data}


menu_api.add_resource(Menus, '/menus/')
