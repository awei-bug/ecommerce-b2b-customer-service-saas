from flask import Blueprint
from flask_restful import Api

cate_bp = Blueprint('category', __name__)
cate_api = Api(cate_bp)


attr_bp = Blueprint('attribute', __name__)
attr_api = Api(attr_bp)

from . import views