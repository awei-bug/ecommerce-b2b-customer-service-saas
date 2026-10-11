# -*- coding: utf-8 -*-
"""Create the tenant-scoped store knowledge table and menu entry."""
from __future__ import annotations

import json
import os
import sys

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
        child = models.Menu.query.filter_by(path="knowledge_base").first()
        if not child:
            child = models.Menu(name="客服知识库", path="knowledge_base", level=2, pid=parent.id)
            db.session.add(child)
            db.session.flush()
        for role in models.Role.query.filter_by(name="客服").all():
            menu_ids = {item.id for item in (role.menus or [])}
            if child.id not in menu_ids:
                role.menus.append(child)
            try:
                codes = set(json.loads(role.perm_codes or "[]"))
            except (TypeError, ValueError):
                codes = set()
            codes.add("service:read")
            role.perm_codes = json.dumps(sorted(codes), ensure_ascii=False)
        db.session.commit()
        print("store knowledge schema and menu ready")


if __name__ == "__main__":
    main()
