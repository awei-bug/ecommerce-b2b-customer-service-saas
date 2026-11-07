"""在目标库显式创建 t_domain_events。

生产模式启动只做 schema 只读核查，不会自动建表。新增模型后必须先在
目标库执行本脚本，否则 create_app 会因 schema_problems 直接失败。
表结构由 models.DomainEvent 单一定义，本脚本不重复声明字段，方言由
SQLAlchemy 依据 DATABASE_URL 自动适配 MySQL 与 PostgreSQL。

用法：
    DATABASE_URL=... python scripts/create_domain_events_table.py --confirm-database flask_shop
"""
import argparse
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine, inspect  # noqa: E402
from flask_shop import db  # noqa: E402
import flask_shop.models  # noqa: E402,F401  注册全部表到 metadata


def main():
    parser = argparse.ArgumentParser(description='显式创建领域事件表')
    parser.add_argument('--confirm-database', required=True,
                        help='显式确认目标库名，与 DATABASE_URL 中的库名必须一致')
    args = parser.parse_args()

    url = os.environ.get('DATABASE_URL', '').strip()
    if not url:
        raise SystemExit('必须显式设置 DATABASE_URL，拒绝隐式使用默认连接')

    dbname = (urlparse(url).path or '').lstrip('/')
    if not dbname or dbname != args.confirm_database:
        raise SystemExit(
            f'库名不匹配，URL 指向 {dbname!r}，确认值为 {args.confirm_database!r}'
        )

    engine = create_engine(url, future=True)
    table = db.metadata.tables['t_domain_events']
    try:
        if inspect(engine).has_table(table.name):
            print(f'{table.name} 已存在，无需创建')
            return 0
        table.create(engine, checkfirst=True)
        print(f'已创建 {table.name}，方言 {engine.dialect.name}')
        return 0
    finally:
        engine.dispose()


if __name__ == '__main__':
    raise SystemExit(main())
