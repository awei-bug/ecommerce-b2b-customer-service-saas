# -*- coding: utf-8 -*-
"""将 deploy/backups 下某个 sql 恢复到临时库 flask_shop_restore（不覆盖正式库）。"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

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
RESTORE_DB = os.getenv("RESTORE_DB", "flask_shop_restore")


def main():
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

    sql = sql_path.read_text(encoding="utf-8", errors="replace")
    conn = pymysql.connect(host=HOST, port=PORT, user=USER, password=PWD, charset="utf8mb4", autocommit=True)
    cur = conn.cursor()
    cur.execute(f"DROP DATABASE IF EXISTS `{RESTORE_DB}`")
    cur.execute(
        f"CREATE DATABASE `{RESTORE_DB}` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
    )
    cur.execute(f"USE `{RESTORE_DB}`")
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
    print(f"RESTORE_OK db={RESTORE_DB} statements_ok={ok} fail={fail} tables={len(tables)}")
    print("正式库 flask_shop 未被覆盖。确认无误后可手工导入正式库。")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
