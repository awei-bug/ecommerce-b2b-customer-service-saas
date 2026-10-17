# 数据库迁移与 Schema 管理

> 决策（2026-10-17）：**不使用 Alembic / Flask-Migrate**。见下方「为什么不用 Alembic」。

## 结论：schema 由三部分协作

1. **启动自愈**：`flask_shop/__init__.py` 的 `ensure_schema_compat()` 在每次启动时执行
   - 幂等补列（硬编码 `ALTER TABLE ... ADD COLUMN` 列表，仅 MySQL 方言）
   - `db.create_all()` 补齐缺失的新表（模型新增字段/表后重启即生效）
   - 已按「预期失败静默、真实故障告警」区分记录日志（见 `_is_already_exists`）
2. **一次性功能迁移**：`scripts/migrations/migrate_*.py`（纯 SQLAlchemy，无 Alembic 依赖）
   - 每个脚本独立幂等（`create_all()` 或 `column_exists` / `inspect` 守卫）
   - 用于老库的列变更、数据回填、历史数据修正
3. **建库与备份**：`deploy/` 下脚本（docker-compose 建 MySQL、backup_all.sh / backup_mysql.sh 备份）

## 为什么不用 Alembic

- 实测 `flask db upgrade` 在全新库上**必然失败**：`create_app` 内的 `db.create_all()` 会抢先建出全部表，Alembic 第一个版本再 `create table` 就报 `table t_users already exists`。
- 部署链路（`deploy/Dockerfile.api`、`docker_bootstrap.sh`、CI）**从未调用过 alembic**；容器只是启动 gunicorn，schema 靠 `ensure_schema_compat` 兜底。
- 全项目只有 `manager.py` 和 `wsgi.py` 两处注册过 `Migrate(app, db)`，没有任何脚本调用 `flask db`。2026-10-17 已移除这两处注册，并从 `requirements.txt` 删除 `Flask-Migrate` / `alembic`，避免新人误跑。
- `migrations/versions/*.py`（15 个 Alembic 版本）仅作为历史 schema 演进参考保留，**已废弃**。

## 全新部署流程（建库）

1. 启动 MySQL 并建空库（`deploy/docker-compose.yml`，或 `deploy/docker_bootstrap.sh`）。
2. 首次启动 API → `create_app` → `ensure_schema_compat` 自动建全表。
3. 按需执行 `scripts/seeds/*.py` 导入基础/演示数据。
4. 冒烟验证（healthcheck 通过、登录、下单各一次）。

## 存量库升级流程

1. 先备份（`deploy/backup_all.sh`）。
2. 升级代码 → 重启 → `ensure_schema_compat` 自动补列/建新表。
3. 逐个执行本次版本新增的 `scripts/migrations/migrate_*.py`（**先在一台 staging 上跑一遍**再上生产）。

## 新增迁移的规范

- **建新表**：直接在模型中定义，重启后由 `db.create_all()` 自动建，无需写迁移脚本。
- **改已有表 / 回填数据**：新建 `scripts/migrations/migrate_<feature>.py`，必须满足：
  - 幂等：先用 `inspect` 或 `column_exists(table, column)` 判断再执行；
  - docstring 写清用法与目的（参照现有脚本的格式）；
  - 只写 MySQL 兼容 DDL。
- **不要**把永久业务逻辑堆进 `ensure_schema_compat` 的硬编码列表；那里只放「启动自愈」级别的兼容补列。

## 已知约束

- `ensure_schema_compat` 的硬编码 DDL 是 **MySQL 方言**（含 12 条 `MODIFY COLUMN ... DECIMAL(12,2)`）。在 sqlite（测试/CI）下这些语句会报语法错误并被记入告警日志 —— 属预期行为，不是 bug。
- 老库升级时 `scripts/migrations` 需按功能顺序执行；个别历史脚本未逐条验证幂等，正式跑前务必在 staging 验证。

## 后续正规化（Plan A，尚未做）

把 `ensure_schema_compat` + `scripts/migrations` 归并进真正的版本链需要：
1. `create_app` 不再无条件 `create_all`；
2. 存量库基线化到版本链；
3. 定义升级顺序、回滚与数据校验。
这是独立工程，不在当前交付路径上。
