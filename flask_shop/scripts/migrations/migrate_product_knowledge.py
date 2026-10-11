"""创建 t_product_knowledge（数据中心知识缓存表）"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from flask_shop import create_app, db, models  # noqa: E402

app = create_app('develop')


def main():
    with app.app_context():
        db.create_all()
        print('OK', models.ProductKnowledge.__tablename__)


if __name__ == '__main__':
    main()
