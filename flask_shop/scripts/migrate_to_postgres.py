"""MySQL -> PostgreSQL migration for the shop database.

Idempotent: re-running skips tables that are already populated and refuses to
overwrite a non-empty target unless --replace is given. Source is opened
read-only. Prints a per-table reconciliation table.

Usage (from flask_shop/):
    .venv/Scripts/python.exe scripts/migrate_to_postgres.py \
        --target postgresql+psycopg://user:pw@127.0.0.1:5432/flask_shop
"""

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pymysql  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

from flask_shop import db, models  # noqa: E402,F401


def parse_args():
    parser = argparse.ArgumentParser(description='把商城数据从 MySQL 迁移到 PostgreSQL')
    parser.add_argument('--target', required=True, help='目标 PostgreSQL URL')
    parser.add_argument('--source-host', default=os.getenv('MYSQL_HOST', '127.0.0.1'))
    parser.add_argument('--source-port', type=int, default=int(os.getenv('MYSQL_PORT', '3307')))
    parser.add_argument('--source-user', default=os.getenv('MYSQL_USERNAME', 'root'))
    parser.add_argument('--source-password', default=os.getenv('MYSQL_PASSWORD', ''))
    parser.add_argument('--source-db', default=os.getenv('MYSQL_DB', 'flask_shop'))
    parser.add_argument('--replace', action='store_true', help='目标非空时也继续（会先清空目标表）')
    parser.add_argument('--dry-run', action='store_true', help='只对账，不写入')
    parser.add_argument('--allow-unmapped-tables', default='',
                        help='逗号分隔，显式允许跳过的源端未建模表；未列出的表会拒绝迁移')
    parser.add_argument('--allow-column-loss', action='store_true',
                        help='允许丢弃含数据的未建模列，默认拒绝')
    return parser.parse_args()


def find_unmapped_tables(source_tables, orm_tables):
    """源库有、ORM 没有的表。整表数据会留在源端，必须显式确认。"""
    return sorted(set(source_tables) - set(orm_tables))


def classify_source_columns(cols, target_cols, rows):
    """返回可迁移列、被丢弃列、以及丢弃列中非空的行数。"""
    keep = [c for c in cols if c in target_cols]
    skip = [c for c in cols if c not in target_cols]
    if not skip:
        return keep, skip, 0
    idx = [cols.index(c) for c in skip]
    nonnull = sum(1 for row in rows if any(row[i] is not None for i in idx))
    return keep, skip, nonnull


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    args = parse_args()

    target = create_engine(args.target)
    db.metadata.create_all(bind=target)

    source = pymysql.connect(
        host=args.source_host,
        port=args.source_port,
        user=args.source_user,
        password=args.source_password,
        database=args.source_db,
        charset='utf8mb4',
        cursorclass=pymysql.cursors.Cursor,
    )
    cur = source.cursor()

    cur.execute('SHOW TABLES')
    source_tables = [row[0] for row in cur.fetchall()]
    allowed_unmapped = {
        item.strip() for item in args.allow_unmapped_tables.split(',') if item.strip()
    }
    unmapped = find_unmapped_tables(source_tables, db.metadata.tables.keys())
    unexpected = [name for name in unmapped if name not in allowed_unmapped]
    if unexpected:
        print('拒绝执行：源库存在 ORM 未建模的表，这些整表数据会留在 MySQL：')
        for name in unexpected:
            cur.execute('SELECT COUNT(*) FROM `%s`' % name)
            print('  %s (%s 行)' % (name, cur.fetchone()[0]))
        print('请补齐模型，或用 --allow-unmapped-tables 显式列出允许跳过的表。')
        return 2
    if unmapped:
        print('以下源端表未建模，已显式确认跳过，数据仍留在 MySQL：')
        for name in unmapped:
            print('  ' + name)

    # 父表优先：按 ORM 外键做拓扑排序
    ordered, seen = [], set()

    def visit(name, stack=()):
        if name in seen or name in stack:
            return
        for fk in db.metadata.tables[name].foreign_keys:
            parent = fk.column.table.name
            if parent in db.metadata.tables:
                visit(parent, stack + (name,))
        if name not in seen:
            seen.add(name)
            ordered.append(name)

    for table in sorted(db.metadata.tables):
        visit(table)

    # 目标非空检查
    with target.connect() as conn:
        occupied = []
        for name in ordered:
            n = conn.execute(text('SELECT COUNT(*) FROM "%s"' % name)).scalar()
            if n:
                occupied.append((name, n))
    if occupied and not args.replace:
        print('拒绝执行：目标库非空，拒绝覆盖：')
        for name, n in occupied[:12]:
            print('  %s=%d' % (name, n))
        print('如确需覆盖请显式传入 --replace')
        return 2

    if args.replace and occupied:
        with target.begin() as conn:
            for name, _ in occupied:
                conn.execute(text('TRUNCATE TABLE "%s" CASCADE' % name))
        print('已清空目标表:', len(occupied))

    if args.dry_run:
        print('--dry-run：只对账，不写入')

    with target.begin() as conn:
        conn.execute(text('SET session_replication_role = replica'))

    rows_out, dropped, failed, data_loss = [], [], [], []
    for name in ordered:
        try:
            cur.execute('SELECT COUNT(*) FROM `%s`' % name)
            src = cur.fetchone()[0]

            if src:
                cur.execute('SELECT * FROM `%s`' % name)
                cols = [d[0] for d in cur.description]
                data = cur.fetchall()
                target_cols = {c.name for c in db.metadata.tables[name].columns}
                keep, skip, nonnull = classify_source_columns(cols, target_cols, data)
                if skip:
                    dropped.append((name, skip, nonnull, len(data)))
                    if nonnull and not args.allow_column_loss:
                        data_loss.append((name, skip, nonnull))
                        print('拒绝写入 %s：未建模列 %s 含 %d 行非空数据'
                              % (name, ','.join(skip), nonnull))
                        continue
                if keep and not args.dry_run:
                    collist = ', '.join('"%s"' % c for c in keep)
                    ph = ', '.join(':%s' % c for c in keep)
                    stmt = text('INSERT INTO "%s" (%s) VALUES (%s)' % (name, collist, ph))
                    payload = [
                        dict(zip(keep, [r[cols.index(c)] for c in keep])) for r in data
                    ]
                    with target.begin() as conn:
                        conn.execute(stmt, payload)

            with target.connect() as conn:
                dst = conn.execute(text('SELECT COUNT(*) FROM "%s"' % name)).scalar()
            if src or dst:
                rows_out.append((name, src, dst))
        except Exception as exc:
            failed.append((name, type(exc).__name__, str(exc).split('\n')[0][:120]))

    with target.begin() as conn:
        conn.execute(text('SET session_replication_role = DEFAULT'))

    if rows_out:
        print()
        print('%-34s %8s %8s  %s' % ('表名', '源行数', '目标行数', '一致'))
        for name, src, dst in rows_out:
            print('%-34s %8d %8d  %s' % (name, src, dst, 'OK' if src == dst else 'DIFF'))

    diffs = [r for r in rows_out if r[1] != r[2]]
    print()
    print('合计: mysql=%d pg=%d' % (sum(r[1] for r in rows_out), sum(r[2] for r in rows_out)))
    print('行数不一致:', [r[0] for r in diffs] or '无')
    if dropped:
        print('未迁移的列:')
        for name, skip, nonnull, total in dropped:
            print('  %s: %s (非空 %d/%d)' % (name, ','.join(skip), nonnull, total))
    else:
        print('未迁移的列: 无')
    print('失败表数:', len(failed))
    for f in failed:
        print('  ', f[0], '|', f[1], '|', f[2])

    if data_loss:
        print('拒绝完成：%d 张表存在未建模列且含实际数据，本次未写入这些表。'
              % len(data_loss))
        print('请先补齐模型字段；确需丢弃请显式传入 --allow-column-loss。')
    source.close()
    return 0 if not diffs and not failed and not data_loss else 1


if __name__ == '__main__':
    sys.exit(main())
