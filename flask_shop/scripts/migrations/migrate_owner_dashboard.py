# -*- coding: utf-8 -*-
"""Add the explicit customer-service-to-order attribution field."""
import os
import sys

from sqlalchemy import inspect, text

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from flask_shop import create_app, db  # noqa: E402


def main():
    app = create_app(os.getenv("FLASK_CONFIG", "develop"))
    with app.app_context():
        columns = {item["name"] for item in inspect(db.engine).get_columns("t_order")}
        if "consultation_session_id" not in columns:
            db.session.execute(text("ALTER TABLE t_order ADD COLUMN consultation_session_id VARCHAR(64)"))
            db.session.commit()
        print("owner dashboard schema ready")


if __name__ == "__main__":
    main()
