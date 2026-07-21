from flask import Blueprint

logistics_bp = Blueprint('logistics', __name__)

from . import views  # noqa: E402,F401
