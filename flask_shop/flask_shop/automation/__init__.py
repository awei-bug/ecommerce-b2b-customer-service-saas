from flask import Blueprint


automation_bp = Blueprint('automation', __name__, url_prefix='/api/automation')

from flask_shop.automation import views  # noqa: E402,F401

