# -*- coding: utf-8 -*-
"""本机 MySQL 逻辑备份（不依赖 mysqldump）。"""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

import pymysql

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "deploy" / "backups"
OUT.mkdir(parents=True, exist_ok=True)

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
out_file = OUT / f"{DB}_{ts}.sql"


def esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace("'", "\\'")


def main():
    conn = pymysql.connect(
        host=HOST, port=PORT, user=USER, password=PWD, database=DB, charset="utf8mb4"
    )
    cur = conn.cursor()
    cur.execute("SHOW TABLES")
    tables = [r[0] for r in cur.fetchall()]
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
    out_file.write_text("\n".join(lines), encoding="utf-8")
    conn.close()
    print(f"OK {out_file} tables={len(tables)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
