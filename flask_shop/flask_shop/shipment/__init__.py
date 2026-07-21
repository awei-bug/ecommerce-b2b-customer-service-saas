from flask import Blueprint
from flask_restful import Api

shipment_bp = Blueprint('shipment', __name__)
shipment_api = Api(shipment_bp)

from . import views  # noqa: E402,F401
