"""Explicitly initialize an empty database; never upgrade an existing schema."""
import argparse
import os
import sys
from pathlib import Path

from sqlalchemy import inspect
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description='仅初始化空数据库；不会升级存量库')
    parser.add_argument('--confirm-database', required=True, help='必须与配置中的数据库名称完全一致')
    args = parser.parse_args()

    from flask_shop import create_app, db, models

    app = create_app(os.getenv('FLASK_CONFIG', 'develop'), initialize_schema=False, start_background=False)
    database = make_url(app.config['SQLALCHEMY_DATABASE_URI']).database
    if not database or database == ':memory:' or args.confirm_database != database:
        print('拒绝初始化：数据库名称与确认值不一致或不是持久数据库')
        return 2
    with app.app_context():
        inspector = inspect(db.engine)
        if inspector.get_table_names() or inspector.get_view_names():
            print('拒绝初始化：目标数据库已有表或视图；请备份并制定存量库迁移方案')
            return 2
        print(f'正在初始化空数据库 {database}；执行期间不得有其他应用或迁移进程连接并修改结构。')
        db.create_all()
    print('初始化完成；请继续检查配置、导入必要数据并执行上线验收。')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
