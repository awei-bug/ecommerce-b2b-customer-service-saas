# ⚠️ 废弃目录：本目录不再使用

`migrations/` 下的 Alembic 迁移链（`versions/*.py`、`env.py`、`alembic.ini`）**已废弃（2026-10-17）**。

原因与替代方案见 `docs/operations/migration.md`：

- 实际 schema 管理由 `flask_shop/__init__.py` 的 `ensure_schema_compat()`（启动自愈）+ `scripts/migrations/*.py`（一次性功能迁移）完成。
- `Flask-Migrate` / `alembic` 已从 `requirements.txt` 移除，`flask db` 命令不可用。
- 本目录仅保留作为历史 schema 演进参考。**请不要新增或运行这里的迁移**。
