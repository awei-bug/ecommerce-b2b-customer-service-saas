# -*- coding: utf-8 -*-
"""备份 → 恢复 → 核对，一次完整的恢复演练。

为什么单独做这个脚本
------------------
P0 要求「完成一次有记录的恢复演练」，而不是「存在备份脚本」。此前仓库里有
backup_mysql_local.py 和 restore_mysql_local.py，但没有任何东西把两者串起来并
回答最关键的问题：**恢复出来的库能用吗？**

只恢复到临时库然后打印表数是不够的——那只能证明 SQL 跑完了，不能证明数据还在。
本脚本做三件事：

1. **选备份**：选择现有的可信逻辑备份；
2. **恢复**：把备份恢复到新建的随机临时库；
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
- SQL 备份可包含跨库操作，只能在隔离的 MySQL 实例中执行可信备份。
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
import sys
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import pymysql
from sqlalchemy.engine import make_url

# 脚本位于 flask_shop/scripts/verify/，因此 flask_shop 根是上三级。
FLASK_SHOP_ROOT = Path(__file__).resolve().parents[2]
# config.py（config_map 所在）在 flask_shop 根，与 manager.py 同级。
REPO_ROOT = FLASK_SHOP_ROOT
for _path in (FLASK_SHOP_ROOT,):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from config import config_map  # noqa: E402

BACKUP_DIR = REPO_ROOT.parent / "deploy" / "backups"

# 业务关键表：除行数外还要抽查数据合法性。
KEY_TABLES = ("t_tenants", "t_users", "t_product", "t_order", "t_payments", "t_support_conversations")

CHECKS: list[dict] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    CHECKS.append({"name": name, "ok": bool(ok), "detail": detail})
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  {detail}" if detail else ""))
    return ok


def _connect(database: str | None = None):
    url = _source_url()
    return pymysql.connect(
        host=url.host or "127.0.0.1",
        port=url.port or 3306,
        user=url.username,
        password=url.password or "",
        database=database,
        charset="utf8mb4",
        autocommit=True,
    )


def _source_url():
    url = make_url(config_map["develop"].SQLALCHEMY_DATABASE_URI)
    if url.get_backend_name() != "mysql" or not url.database:
        raise ValueError("恢复演练要求配置 MySQL 数据库")
    if set(url.query) - {"charset"}:
        raise ValueError("数据库连接包含未支持的参数，不能安全推断演练连接")
    return url


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
    if not re.fullmatch(r"shop_rehearsal_[0-9a-f]{32}", restore_db):
        raise ValueError("无效的临时库名称")
    sql = backup_file.read_text(encoding="utf-8")
    if not sql.strip():
        raise ValueError("备份文件为空")
    conn = _connect()
    cursor = conn.cursor()
    try:
        cursor.execute(
            f"CREATE DATABASE `{restore_db}` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
        )
        cursor.execute(f"USE `{restore_db}`")
    except Exception:
        conn.close()
        raise

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

    if os.getenv("RESTORE_DB"):
        print("不再支持 RESTORE_DB：演练仅使用新建的随机临时库")
        return 1
    try:
        source_db = _source_url().database
    except ValueError as exc:
        print(f"数据库配置无效：{exc}")
        return 1
    restore_db = f"shop_rehearsal_{uuid4().hex}"
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
    if not check("backup.size.nonzero", backup_file.stat().st_size > 0, f"{backup_mb} MB"):
        source_conn.close()
        return 1

    # --- 2. 读取当前源库行数作为核对基线 ---
    source_cursor = source_conn.cursor()
    source_counts = _table_counts(source_cursor)
    source_valid = check(
        "source.tables.present",
        bool(source_counts) and all(count >= 0 for count in source_counts.values()),
        f"tables={len(source_counts)}",
    )
    if not source_valid:
        source_conn.close()
        return 1

    # --- 3. 恢复到独立临时库 ---
    try:
        statements_ok, statements_fail = _restore(backup_file, restore_db)
    except Exception as exc:  # noqa: BLE001
        check("restore.executed", False, f"{type(exc).__name__}: {exc}; 临时库名称={restore_db}")
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
        not mismatched and all(count >= 0 for count in restore_counts.values()),
        f"全部 {len(source_counts)} 张表一致" if not mismatched else str(mismatched)[:200],
    )

    # --- 5. 业务关键表的数据合法性抽查 ---
    key_present = [t for t in KEY_TABLES if t in restore_counts]
    check("restore.key.tables.present", len(key_present) == len(KEY_TABLES), f"{len(key_present)}/{len(KEY_TABLES)}")

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
        "source.rowcounts.stable",
        after_counts == source_counts and all(count >= 0 for count in after_counts.values()),
        "源库行数演练前后一致；这不能证明源库未被修改",
    )

    restore_conn.close()
    # --- 7. 清理临时库（除非 --keep）---
    if not args.keep:
        try:
            admin = _connect()
            try:
                admin.cursor().execute(f"DROP DATABASE `{restore_db}`")
            finally:
                admin.close()
            check("restore.cleanup", True, "临时库已删除")
        except Exception as exc:  # noqa: BLE001
            check("restore.cleanup", False, f"清理临时库失败：{exc}")

    source_conn.close()

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
