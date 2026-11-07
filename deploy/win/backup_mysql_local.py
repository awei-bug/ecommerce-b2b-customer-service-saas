# -*- coding: utf-8 -*-
"""本机 MySQL 逻辑备份（不依赖 mysqldump）。"""
from __future__ import annotations

import os
import re
import tempfile
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import pymysql

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "deploy" / "backups"

# 读 flask_shop/.env
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
DB = os.getenv("MYSQL_DB", "flask_shop")

ts = datetime.now().strftime("%Y%m%d_%H%M%S")


def esc(s: str) -> str:
    return pymysql.converters.escape_string(s)


def build_dump(conn):
    cur = conn.cursor()
    cur.execute("SHOW TABLES")
    tables = [r[0] for r in cur.fetchall()]
    if not tables:
        raise ValueError("Database has no tables; backup was not published")
    lines = [
        f"-- backup {DB} @ {HOST}:{PORT} {ts}",
        "SET NAMES utf8mb4;",
        "SET FOREIGN_KEY_CHECKS=0;",
    ]
    for table in tables:
        cur.execute(f"SHOW CREATE TABLE `{table}`")
        create_sql = cur.fetchone()[1]
        lines.append(f"DROP TABLE IF EXISTS `{table}`;")
        lines.append(create_sql + ";")
        cur.execute(f"SELECT * FROM `{table}`")
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
        if not rows:
            continue
        col_list = ",".join(f"`{c}`" for c in cols)
        for row in rows:
            vals = []
            for v in row:
                if v is None:
                    vals.append("NULL")
                elif isinstance(v, (int, float)):
                    vals.append(str(v))
                elif isinstance(v, (bytes, bytearray)):
                    vals.append("0x" + v.hex())
                else:
                    vals.append("'" + esc(str(v)) + "'")
            lines.append(f"INSERT INTO `{table}` ({col_list}) VALUES ({','.join(vals)});")
    lines.append("SET FOREIGN_KEY_CHECKS=1;")
    return lines, len(tables)


def main():
    if not re.fullmatch(r"[A-Za-z0-9_]+", DB):
        raise ValueError("Invalid MYSQL_DB")
    OUT.mkdir(parents=True, exist_ok=True)
    out_file = OUT / f"{DB}_{ts}_{uuid4().hex}.sql"
    conn = pymysql.connect(
        host=HOST, port=PORT, user=USER, password=PWD, database=DB, charset="utf8mb4"
    )
    try:
        lines, table_count = build_dump(conn)
    finally:
        conn.close()
    descriptor, temp_name = tempfile.mkstemp(prefix=".backup-", suffix=".partial", dir=OUT)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as backup:
            backup.write("\n".join(lines))
            backup.flush()
            os.fsync(backup.fileno())
        os.replace(temp_name, out_file)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
    print(f"OK {out_file} tables={table_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
