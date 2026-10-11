# -*- coding: utf-8 -*-
"""Add the explicit tenant data mode used by delivery onboarding."""
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
        columns = {item["name"] for item in inspect(db.engine).get_columns("t_tenants")}
        if "data_mode" not in columns:
            db.session.execute(text("ALTER TABLE t_tenants ADD COLUMN data_mode VARCHAR(16) NOT NULL DEFAULT 'live'"))
        db.session.execute(text("UPDATE t_tenants SET data_mode='demo' WHERE slug='demo' OR slug LIKE 'demo-%'"))
        db.session.execute(text("UPDATE t_tenants SET data_mode='live' WHERE data_mode IS NULL OR data_mode=''"))
        db.session.commit()
        print("tenant onboarding schema ready")


if __name__ == "__main__":
    main()
