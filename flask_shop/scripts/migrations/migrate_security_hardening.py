# -*- coding: utf-8 -*-
"""Create persistent login throttling records for existing databases."""
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
        print('security hardening schema ready: t_login_throttle')


if __name__ == '__main__':
    main()
