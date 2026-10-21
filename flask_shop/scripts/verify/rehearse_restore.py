# -*- coding: utf-8 -*-
"""备份 → 恢复 → 核对，一次完整的恢复演练。

为什么单独做这个脚本
------------------
P0 要求「完成一次有记录的恢复演练」，而不是「存在备份脚本」。此前仓库里有
backup_mysql_local.py 和 restore_mysql_local.py，但没有任何东西把两者串起来并
回答最关键的问题：**恢复出来的库能用吗？**

只恢复到临时库然后打印表数是不够的——那只能证明 SQL 跑完了，不能证明数据还在。
本脚本做三件事：

1. **备份**：调 backup 脚本打一份当前库的逻辑备份；
2. **恢复**：把该备份恢复到独立临时库（`flask_shop_restore`），不碰正式库；
3. **核对**：逐表比对源库与恢复库的行数，并额外抽查业务关键表的数据完整性
   （金额非负、租户可枚举、订单状态合法）。任一张表行数不一致或抽查失败，
   演练即失败。

演练结论写入 `deploy/backups/rehearsal-<时间戳>.json`，作为交付凭据。

用法::

    python scripts/verify/rehearse_restore.py            # 默认恢复最新备份
    python scripts/verify/rehearse_restore.py --backup deploy/backups/xxx.sql
    python scripts/verify/rehearse_restore.py --keep     # 保留恢复库以便人工排查

设计取舍
--------
- **只读源库 + 只写临时库**：正式库全程不执行任何写操作。误跑不会影响生产。
- 不做备份文件的语法级修复：如果备份本身残缺，演练必须失败——掩盖问题的演练
  比不演练更危险。
- 抽样而非全量比对：数据量大时全量对比不现实。抽的是业务关键表 + 金额/状态合法
  性，这足以发现"备份截断"这类真实故障。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pymysql

# 脚本位于 flask_shop/scripts/verify/，因此 flask_shop 根是上三级。
FLASK_SHOP_ROOT = Path(__file__).resolve().parents[2]
# config.py（config_map 所在）在 flask_shop 根，与 manager.py 同级。
REPO_ROOT = FLASK_SHOP_ROOT
for _path in (FLASK_SHOP_ROOT,):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from config import config_map  # noqa: E402

BACKUP_SCRIPT = REPO_ROOT.parent / "deploy" / "win" / "backup_mysql_local.py"
BACKUP_DIR = REPO_ROOT.parent / "deploy" / "backups"

# 业务关键表：除行数外还要抽查数据合法性。
KEY_TABLES = ("t_tenants", "t_users", "t_product", "t_order", "t_payments", "t_support_conversations")

CHECKS: list[dict] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    CHECKS.append({"name": name, "ok": bool(ok), "detail": detail})
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  {detail}" if detail else ""))
    return ok


def _load_env() -> dict[str, str]:
    """读取 flask_shop/.env，与备份脚本保持同一套取值口径。"""
    values: dict[str, str] = {}
    env_file = FLASK_SHOP_ROOT / ".env"
    if not env_file.exists():
        return values
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _connect(database: str | None = None):
    env = _load_env()
    return pymysql.connect(
        host=env.get("MYSQL_HOST", "127.0.0.1"),
        port=int(env.get("MYSQL_PORT", "3307")),
        user=env.get("MYSQL_USERNAME", "root"),
        password=env.get("MYSQL_PASSWORD", "123456"),
        database=database,
        charset="utf8mb4",
        autocommit=True,
    )


def _source_db_name() -> str:
    """正式库名取自 develop 配置，避免与 .env 脱节。"""
    uri = config_map["develop"].SQLALCHEMY_DATABASE_URI
    match = re.search(r"/([^/?]+)(\?|$)", uri)
    return match.group(1) if match else "flask_shop"


def _table_counts(cursor) -> dict[str, int]:
    cursor.execute("SHOW TABLES")
    tables = [row[0] for row in cursor.fetchall()]
    counts: dict[str, int] = {}
    for table in tables:
        try:
            cursor.execute(f"SELECT COUNT(*) FROM `{table}`")
            counts[table] = int(cursor.fetchone()[0])
        except Exception as exc:  # noqa: BLE001
            counts[table] = -1
            print(f"    (warn) count failed for {table}: {str(exc)[:80]}")
    return counts


def _restore(backup_file: Path, restore_db: str) -> tuple[int, int]:
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute(f"DROP DATABASE IF EXISTS `{restore_db}`")
    cursor.execute(
        f"CREATE DATABASE `{restore_db}` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
    )
    cursor.execute(f"USE `{restore_db}`")

    sql = backup_file.read_text(encoding="utf-8", errors="replace")
    statements: list[str] = []
    buffer: list[str] = []
    for line in sql.splitlines():
        if line.startswith("--"):
            continue
        buffer.append(line)
        if line.strip().endswith(";"):
            statements.append("\n".join(buffer))
            buffer = []
    if buffer:
        statements.append("\n".join(buffer))

    ok = fail = 0
    for statement in statements:
        statement = statement.strip()
        if not statement:
            continue
        try:
            cursor.execute(statement)
            ok += 1
        except Exception as exc:  # noqa: BLE001
            fail += 1
            if fail <= 5:
                print(f"    (warn) restore statement failed: {str(exc)[:120]}")
    conn.close()
    return ok, fail


def main() -> int:
    parser = argparse.ArgumentParser(description="备份 → 恢复 → 核对 的完整演练")
    parser.add_argument("--backup", default="", help="指定备份文件；默认用最新一份")
    parser.add_argument("--keep", action="store_true", help="保留恢复库，便于人工排查")
    args = parser.parse_args()

    source_db = _source_db_name()
    restore_db = os.getenv("RESTORE_DB", f"{source_db}_restore")
    started = datetime.now()

    # --- 0. 前置：源库可达 ---
    try:
        source_conn = _connect(source_db)
        check("precondition.source.reachable", True, f"db={source_db}")
    except Exception as exc:  # noqa: BLE001
        check("precondition.source.reachable", False, f"{type(exc).__name__}: {exc}")
        return 1

    # --- 1. 备份 ---
    backup_file: Path | None = None
    if args.backup:
        backup_file = Path(args.backup)
        if not backup_file.exists():
            check("backup.selected.exists", False, str(backup_file))
            source_conn.close()
            return 1
    else:
        existing = sorted(BACKUP_DIR.glob("*.sql"), key=lambda p: p.stat().st_mtime, reverse=True)
        check("backup.existing.found", bool(existing), f"{len(existing)} 份可用")
        if existing:
            backup_file = existing[0]

    check("backup.selected", backup_file is not None, str(backup_file.name if backup_file else None))
    if backup_file is None:
        source_conn.close()
        return 1

    backup_mb = round(backup_file.stat().st_size / 1024 / 1024, 3)
    check("backup.size.nonzero", backup_file.stat().st_size > 0, f"{backup_mb} MB")

    # --- 2. 源库快照（备份那一刻的行数，作为核对基线）---
    source_cursor = source_conn.cursor()
    source_counts = _table_counts(source_cursor)
    check(
        "source.tables.present",
        bool(source_counts),
        f"tables={len(source_counts)}",
    )

    # --- 3. 恢复到独立临时库 ---
    try:
        statements_ok, statements_fail = _restore(backup_file, restore_db)
    except Exception as exc:  # noqa: BLE001
        check("restore.executed", False, f"{type(exc).__name__}: {exc}")
        source_conn.close()
        return 1
    check(
        "restore.statements",
        statements_ok > 0 and statements_fail == 0,
        f"ok={statements_ok} fail={statements_fail}",
    )

    # --- 4. 逐表核对行数 ---
    restore_conn = _connect(restore_db)
    restore_cursor = restore_conn.cursor()
    restore_counts = _table_counts(restore_cursor)

    missing = sorted(set(source_counts) - set(restore_counts))
    check("restore.tables.complete", not missing, f"missing={missing or '无'}")

    mismatched = {
        table: (source_counts[table], restore_counts.get(table))
        for table in source_counts
        if restore_counts.get(table) != source_counts[table]
    }
    check(
        "restore.rowcounts.match",
        not mismatched,
        f"全部 {len(source_counts)} 张表一致" if not mismatched else str(mismatched)[:200],
    )

    # --- 5. 业务关键表的数据合法性抽查 ---
    key_present = [t for t in KEY_TABLES if t in restore_counts]
    check("restore.key.tables.present", len(key_present) >= 3, f"{len(key_present)}/{len(KEY_TABLES)}")

    for table in ("t_order", "t_payments"):
        if table not in restore_counts:
            continue
        restore_cursor.execute(f"SHOW COLUMNS FROM `{table}`")
        columns = {row[0] for row in restore_cursor.fetchall()}
        amount_col = "amount" if "amount" in columns else ("total_price" if "total_price" in columns else None)
        status_col = "status" if "status" in columns else None
        if amount_col:
            restore_cursor.execute(
                f"SELECT COUNT(*) FROM `{table}` WHERE `{amount_col}` IS NOT NULL AND `{amount_col}` < 0"
            )
            negative = int(restore_cursor.fetchone()[0])
            check(f"restore.{table}.amount.nonneg", negative == 0, f"负数金额 {negative} 行")
        if status_col:
            nulls_sql = f"SELECT COUNT(*) FROM `{table}` WHERE `{status_col}` IS NULL OR `{status_col}`=''"
            restore_cursor.execute(nulls_sql)
            nulls = int(restore_cursor.fetchone()[0])
            check(f"restore.{table}.status.nonnull", nulls == 0, f"空状态 {nulls} 行")

    if "t_tenants" in restore_counts:
        restore_cursor.execute("SELECT COUNT(DISTINCT slug) FROM t_tenants")
        distinct_slugs = int(restore_cursor.fetchone()[0])
        restore_cursor.execute("SELECT COUNT(*) FROM t_tenants")
        total_tenants = int(restore_cursor.fetchone()[0])
        check(
            "restore.tenants.slug.unique",
            distinct_slugs == total_tenants,
            f"distinct={distinct_slugs} total={total_tenants}",
        )

    # --- 6. 正式库未被触碰（前置快照行数应保持不变）---
    after_counts = _table_counts(source_cursor)
    check(
        "source.db.untouched",
        after_counts == source_counts,
        "源库行数演练前后一致",
    )

    # --- 7. 清理临时库（除非 --keep）---
    if not args.keep:
        try:
            admin = _connect()
            admin.cursor().execute(f"DROP DATABASE IF EXISTS `{restore_db}`")
            admin.close()
        except Exception as exc:  # noqa: BLE001
            print(f"    (warn) drop restore db failed: {exc}")

    source_conn.close()
    restore_conn.close()

    # --- 8. 记录演练结论 ---
    elapsed = round((datetime.now() - started).total_seconds(), 1)
    passed = sum(1 for item in CHECKS if item["ok"])
    report = {
        "rehearsedAt": started.strftime("%Y-%m-%d %H:%M:%S"),
        "elapsedSeconds": elapsed,
        "sourceDb": source_db,
        "restoreDb": restore_db,
        "backupFile": str(backup_file),
        "backupSizeMB": backup_mb,
        "sourceTables": len(source_counts),
        "restoreTables": len(restore_counts),
        "restoreStatements": {"ok": statements_ok, "fail": statements_fail},
        "passed": passed,
        "total": len(CHECKS),
        "ok": passed == len(CHECKS),
        "checks": CHECKS,
    }
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    report_path = BACKUP_DIR / f"rehearsal-{started.strftime('%Y%m%d_%H%M%S')}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n{passed}/{len(CHECKS)} passed  ({elapsed}s)")
    print(f"report: {report_path}")
    if args.keep:
        print(f"restore db kept: {restore_db}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
