# -*- coding: utf-8 -*-
"""Create customer-service conversation tables and menu entries."""
import os
import sys
import json

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from flask_shop import create_app, db, models  # noqa: E402


def main():
    app = create_app(os.getenv("FLASK_CONFIG", "develop"))
    with app.app_context():
        db.create_all()
        parent = models.Menu.query.filter_by(path="service").first()
        if not parent:
            parent = models.Menu(name="客服中心", path="service", level=1)
            db.session.add(parent)
            db.session.flush()
        child = models.Menu.query.filter_by(path="customer_service").first()
        if not child:
            child = models.Menu(name="客服工作台", path="customer_service", level=2, pid=parent.id)
            db.session.add(child)
            db.session.flush()
        support_roles = models.Role.query.filter_by(name="客服").all()
        for support_role in support_roles:
            menu_ids = {item.id for item in (support_role.menus or [])}
            if child.id not in menu_ids:
                support_role.menus.append(child)
            try:
                codes = set(json.loads(support_role.perm_codes or "[]"))
            except (TypeError, ValueError):
                codes = set()
            codes.update({"service:read", "service:reply"})
            support_role.perm_codes = json.dumps(sorted(codes), ensure_ascii=False)
        db.session.commit()
        print("support center schema and menus ready")


if __name__ == "__main__":
    main()
