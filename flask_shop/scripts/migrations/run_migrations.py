# -*- coding: utf-8 -*-
"""统一的 schema 迁移 runner：按依赖顺序执行所有 migrate_*.py。

背景与设计取舍
--------------
本项目**不用 Alembic**（决策见 docs/operations/migration.md）：schema 由启动自愈
（ensure_schema_compat + create_all）+ 幂等 scripts/migrations/*.py 组成。此前
14 个脚本既没有版本号也没有 runner，升级存量库只能靠人工按功能顺序逐个执行——
漏一个或顺序错（例如先跑 store_knowledge 再跑 rbac_actions，写 perm_codes 会
直接失败），线上排错成本很高。

这个 runner 只做三件事，**不替代任何脚本的逻辑**：

1. **固定顺序**：按真实依赖编排，不靠使用者记忆。
2. **断点续跑**：已执行的脚本记入 `schema_migrations` 表，重复运行只跑新脚本。
   注意：脚本本身都幂等，"跳过"只是为了省时间，不是因为不能重跑。
3. **失败即停**：任一脚本失败立刻中止并汇报进度，避免在残缺 schema 上继续跑。

与 Alembic 的关系：这是"顺序清单 + 执行记录"，不是版本链。不做 downgrade，
不做 diff 生成。将来若要走 Alembic（Plan A），这个表可以直接当 version 表用。
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

MIGRATIONS_DIR = Path(__file__).resolve().parent


# 执行顺序。顺序由依赖决定，不是字典序：
#   1. l0_ops / create_all 类先跑：后续脚本的 ALTER TABLE 需要表已存在
#   2. rbac_actions 必须在任何写 perm_codes 的脚本之前，否则缺列直接报错
#   3. store_knowledge / support_center / owner_dashboard 都写 Menu/Role，
#      且 owner_dashboard 要给 t_order 加 consultation_session_id 列，
#      所以 order_payment（建 t_order 相关列）要排在它前面
#   4. tenant_onboarding 最后跑：它按 slug 回填 data_mode，需要租户表稳定
# 追加新脚本时改这里，并在 PR 里说明依赖理由。
ORDER: list[str] = [
    "migrate_l0_ops.py",
    "migrate_customer_auth.py",
    "migrate_sku.py",
    "migrate_commercial_manual_pay.py",
    "migrate_order_payment.py",
    "migrate_rbac_actions.py",
    "migrate_security_hardening.py",
    "migrate_owner_dashboard.py",
    "migrate_l1_features.py",
    "migrate_product_knowledge.py",
    "migrate_store_knowledge.py",
    "migrate_support_center.py",
    "migrate_agent_memory.py",
    "migrate_tenant_onboarding.py",
]

# 每个脚本在这个 runner 里的标识（与文件名解耦，改名不会丢执行记录）。
SLUGS: dict[str, str] = {name: name.removesuffix(".py") for name in ORDER}


class MigrationError(RuntimeError):
    """某个迁移脚本执行失败。"""


def _load_runner_module(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise MigrationError(f"无法加载迁移脚本：{path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_one(path: Path) -> None:
    """执行单个迁移脚本。

    脚本有两种约定：`main()` 或 `migrate()`，两种都支持（历史原因）。
    """
    module = _load_runner_module(path)
    entry = getattr(module, "main", None) or getattr(module, "migrate", None)
    if entry is None or not callable(entry):
        raise MigrationError(f"{path.name} 既没有 main() 也没有 migrate()")


def _ensure_history_table(db) -> None:
    from sqlalchemy import text

    db.session.execute(
        text(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "name VARCHAR(128) NOT NULL PRIMARY KEY,"
            "applied_at DATETIME NULL,"
            "elapsed_ms INTEGER NULL,"
            "status VARCHAR(16) NULL,"
            "message TEXT NULL)"
        )
    )
    db.session.commit()


def _already_applied(db, name: str) -> bool:
    from sqlalchemy import text

    row = db.session.execute(
        text("SELECT name FROM schema_migrations WHERE name = :n AND status = 'ok'"),
        {"n": name},
    ).first()
    return row is not None


def _record(db, name: str, ok: bool, elapsed_ms: int, message: str = "") -> None:
    """写入执行记录。MySQL 与 SQLite 的 upsert 语法不同，分别处理。

    不用 `ON DUPLICATE KEY UPDATE`：那是 MySQL 专有语法，本项目测试与部分部署
    用 SQLite，会在第一条记录处直接语法错误（已实测踩到）。
    """
    dialect = db.engine.dialect.name
    applied_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    payload = message[:500]
    if dialect == "sqlite":
        db.session.execute(
            text(
                "INSERT INTO schema_migrations (name, applied_at, elapsed_ms, status, message) "
                "VALUES (:n, :t, :e, :s, :m) "
                "ON CONFLICT(name) DO UPDATE SET applied_at=excluded.applied_at,"
                " elapsed_ms=excluded.elapsed_ms, status=excluded.status, message=excluded.message"
            ),
            {"n": name, "t": applied_at, "e": elapsed_ms, "s": "ok" if ok else "failed", "m": payload},
        )
    else:
        db.session.execute(
            text(
                "INSERT INTO schema_migrations (name, applied_at, elapsed_ms, status, message) "
                "VALUES (:n, :t, :e, :s, :m) "
                "ON DUPLICATE KEY UPDATE applied_at=VALUES(applied_at), elapsed_ms=VALUES(elapsed_ms),"
                " status=VALUES(status), message=VALUES(message)"
            ),
            {"n": name, "t": applied_at, "e": elapsed_ms, "s": "ok" if ok else "failed", "m": payload},
        )
    db.session.commit()


def main() -> int:
    parser = argparse.ArgumentParser(description="按依赖顺序执行全部 schema 迁移")
    parser.add_argument("--dry-run", action="store_true", help="只打印顺序，不执行")
    parser.add_argument(
        "--force",
        action="store_true",
        help="无视 schema_migrations 记录全部重跑（脚本本身幂等，用于怀疑记录不准时）",
    )
    parser.add_argument(
        "--only",
        default="",
        help="只跑指定脚本（逗号分隔子树名，例如 migrate_sku）",
    )
    args = parser.parse_args()

    # 校验 ORDER 与目录一致：漏登记的新脚本必须显式决定位置，不能悄悄不跑。
    on_disk = {p.name for p in MIGRATIONS_DIR.glob("migrate_*.py")}
    missing = sorted(on_disk - set(ORDER))
    if missing:
        print(f"[runner] 发现未登记的迁移脚本：{', '.join(missing)}")
        print("[runner] 请把它们加进 ORDER 并说明依赖理由，否则它们永远不会被执行。")
        return 2

    targets = ORDER
    if args.only:
        wanted = {s.strip() for s in args.only.split(",") if s.strip()}
        targets = []
        for name in ORDER:
            slug = SLUGS[name]
            if slug in wanted or name in wanted:
                targets.append(name)
        if not targets:
            print(f"[runner] --only 没有匹配到任何脚本：{args.only}")
            return 2

    if args.dry_run:
        print(f"[runner] 将按以下顺序执行 {len(targets)} 个迁移：")
        for index, name in enumerate(targets, 1):
            print(f"  {index:>2}. {name}")
        return 0

    os.environ.setdefault("FLASK_CONFIG", "develop")

    from sqlalchemy import text  # noqa: PLC0415

    from flask_shop import create_app, db  # noqa: PLC0415

    app = create_app(os.getenv("FLASK_CONFIG", "develop"))
    exit_code = 0
    with app.app_context():
        _ensure_history_table(db)
        done = skipped = 0
        for name in targets:
            path = MIGRATIONS_DIR / name
            if not path.exists():
                print(f"[runner] SKIP  {name}（文件不存在）")
                continue
            if not args.force and _already_applied(db, SLUGS[name]):
                print(f"[runner] DONE  {name}（已完成，跳过；--force 可重跑）")
                skipped += 1
                continue
            print(f"[runner] RUN   {name} ...")
            started = time.time()
            try:
                _run_one(path)
            except Exception as exc:  # noqa: BLE001
                elapsed = int((time.time() - started) * 1000)
                _record(db, SLUGS[name], False, elapsed, str(exc))
                print(f"[runner] FAIL  {name}  {type(exc).__name__}: {exc}")
                print(f"[runner] 已中止。前 {done} 个成功、{skipped} 个跳过。")
                print("[runner] 修复后重跑同一命令即可，已成功的不会重复执行。")
                exit_code = 1
                break
            elapsed = int((time.time() - started) * 1000)
            _record(db, SLUGS[name], True, elapsed)
            done += 1
            print(f"[runner] OK    {name}  {elapsed}ms")

        rows = db.session.execute(
            text(
                "SELECT name, applied_at, elapsed_ms, status FROM schema_migrations "
                "ORDER BY name"
            )
        ).all()
        if rows:
            print("\n[runner] 执行记录：")
            for row in rows:
                mark = "ok" if row.status == "ok" else f"! {row.status}"
                print(f"  {mark:<10} {row.name:<34} {row.elapsed_ms or 0}ms  {row.applied_at}")
        print(f"\n[runner] 本次成功 {done}，跳过 {skipped}，历史记录 {len(rows)} 条。")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
