from flask import Blueprint
from flask_restful import Api

pay_bp = Blueprint('pay', __name__, url_prefix='/pay')
pay_api = Api(pay_bp)

from . import views  # noqa: E402,F401
