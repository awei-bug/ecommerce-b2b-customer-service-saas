# -*- coding: utf-8 -*-
"""创建持久化导购记忆表。用法：python scripts/migrations/migrate_agent_memory.py"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from flask_shop import create_app, db  # noqa: E402


def main():
    app = create_app(os.getenv('FLASK_CONFIG', 'develop'))
    with app.app_context():
        db.create_all()
        print('agent memory schema ready')


if __name__ == '__main__':
    main()
