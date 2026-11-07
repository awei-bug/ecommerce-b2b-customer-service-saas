# -*- coding: utf-8 -*-
"""将可信 SQL 备份恢复到新建的随机临时库。"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from uuid import uuid4

import pymysql

ROOT = Path(__file__).resolve().parents[2]
BACKUP_DIR = ROOT / "deploy" / "backups"
env = ROOT / "flask_shop" / ".env"
if env.exists():
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

HOST = os.getenv("MYSQL_HOST", "127.0.0.1")
PORT = int(os.getenv("MYSQL_PORT", "3307"))
USER = os.getenv("MYSQL_USERNAME", "root")
PWD = os.getenv("MYSQL_PASSWORD", "123456")


def main():
    if os.getenv("RESTORE_DB"):
        print("RESTORE_DB is no longer supported; a new random database is required")
        return 1
    if len(sys.argv) < 2:
        files = sorted(BACKUP_DIR.glob("*.sql"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not files:
            print("no backups in", BACKUP_DIR)
            return 1
        sql_path = files[0]
        print("use latest", sql_path.name)
    else:
        sql_path = Path(sys.argv[1])
    if not sql_path.exists():
        print("not found", sql_path)
        return 1

    try:
        sql = sql_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        print("cannot read backup:", exc)
        return 1
    if not sql.strip():
        print("backup is empty")
        return 1
    restore_db = f"shop_restore_{uuid4().hex}"
    conn = pymysql.connect(host=HOST, port=PORT, user=USER, password=PWD, charset="utf8mb4", autocommit=True)
    cur = conn.cursor()
    try:
        cur.execute(
            f"CREATE DATABASE `{restore_db}` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
        )
        cur.execute(f"USE `{restore_db}`")
    except Exception:
        conn.close()
        raise
    # naive split on ;\n
    statements = []
    buf = []
    for line in sql.splitlines():
        if line.startswith("--"):
            continue
        buf.append(line)
        if line.strip().endswith(";"):
            statements.append("\n".join(buf))
            buf = []
    if buf:
        statements.append("\n".join(buf))
    ok, fail = 0, 0
    for st in statements:
        st = st.strip()
        if not st:
            continue
        try:
            cur.execute(st)
            ok += 1
        except Exception as e:
            fail += 1
            if fail <= 5:
                print("warn", str(e)[:120])
    cur.execute(f"SHOW TABLES")
    tables = cur.fetchall()
    print(f"{'RESTORE_OK' if fail == 0 and ok > 0 else 'RESTORE_FAILED'} db={restore_db} statements_ok={ok} fail={fail} tables={len(tables)}")
    print("临时库已保留，检查后请由管理员确认并删除。只应恢复可信备份至隔离的 MySQL 实例。")
    conn.close()
    return 0 if fail == 0 and ok > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
