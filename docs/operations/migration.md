# 数据库迁移与 Schema 管理

> 决策（2026-10-17）：**不使用 Alembic / Flask-Migrate**。见下方「为什么不用 Alembic」。

## 结论：schema 由三部分协作

1. **启动检查与开发自愈**：生产启动只读检查模型所需表、列和 MySQL 精确数值类型，不执行 schema DDL；开发和样板模式仍会运行 `ensure_schema_compat()`。
   - 幂等补列（硬编码 `ALTER TABLE ... ADD COLUMN` 列表，仅 MySQL 方言）
   - `db.create_all()` 补齐缺失的新表（模型新增字段/表后重启即生效）
   - 已按「预期失败静默、真实故障告警」区分记录日志（见 `_is_already_exists`）
2. **一次性功能迁移**：`scripts/migrations/migrate_*.py`（纯 SQLAlchemy，无 Alembic 依赖）
   - 部分脚本使用 `create_all()` 或 `column_exists` / `inspect` 守卫，但完整幂等性尚未验证
   - 用于老库的列变更、数据回填、历史数据修正
3. **建库与备份**：`deploy/` 下脚本（docker-compose 建 MySQL、backup_all.sh / backup_mysql.sh 备份）

## 为什么不用 Alembic

- 实测 `flask db upgrade` 在全新库上**必然失败**：`create_app` 内的 `db.create_all()` 会抢先建出全部表，Alembic 第一个版本再 `create table` 就报 `table t_users already exists`。
- 既有部署链路没有使用 alembic；生产启动现已改为只读结构检查，初始化与升级必须显式处理。
- 全项目只有 `manager.py` 和 `wsgi.py` 两处注册过 `Migrate(app, db)`，没有任何脚本调用 `flask db`。2026-10-17 已移除这两处注册，并从 `requirements.txt` 删除 `Flask-Migrate` / `alembic`，避免新人误跑。
- `migrations/versions/*.py`（15 个 Alembic 版本）仅作为历史 schema 演进参考保留，**已废弃**。

## 全新部署流程（建库）

1. 启动 MySQL 并建空库（`deploy/docker-compose.yml`，或 `deploy/docker_bootstrap.sh`）。
2. 对**确认无任何表和视图**的目标库执行 `python scripts/migrations/init_empty_schema.py --confirm-database <数据库名>`；生产环境设 `FLASK_CONFIG=product` 并使用部署配置。命令会实际建表，不处理存量库；务必先核对目标实例、配置和数据库名，执行期间禁止其他进程并发改库。失败可能留下部分表，需先审查，不可盲目重试。
3. 按需执行 `scripts/seeds/*.py` 导入基础/演示数据。
4. 冒烟验证（healthcheck 通过、登录、下单各一次）。

## 存量库升级流程

1. 先备份（`deploy/backup_all.sh`）。
2. 在隔离实例审查实际结构、金额字段属性和数据，制定并验证显式升级方案。生产 API 启动不会自动补列或建表，结构不匹配会拒绝启动。
3. **暂勿依赖统一 runner 或历史成功记录进行升级**。其执行入口已暂停；必须先完成脚本审计及隔离环境演练，确认目标库的实际结构和数据后再制定逐项升级方案。

## 迁移 runner（执行暂停）

**重要：runner 的历史版本没有调用脚本入口，却可能写入成功记录。** `schema_migrations` 中的历史记录不能证明迁移已执行。历史脚本还存在配置选择、启动副作用以及幂等性待核验的问题，runner 目前只允许查看顺序，其他执行方式一律拒绝（包括 `--force` 和 `--only`）。不要直接逐个运行这些脚本作为替代。

```powershell
cd flask_shop
python scripts/migrations/run_migrations.py --dry-run  # 只看顺序，不执行
```

以下是修复完成后的设计目标，**并非当前可用功能**：

- **固定顺序**：`run_migrations.py` 顶部的 `ORDER` 按真实依赖编排，不是字典序。
  关键约束：`rbac_actions` 必须早于任何写 `perm_codes` 的脚本（否则缺列直接报错）；
  `order_payment` 必须早于 `owner_dashboard`（后者要给 `t_order` 加列）；
  `tenant_onboarding` 最后跑（按 slug 回填 `data_mode`，需要租户表稳定）。
- **断点续跑**：执行记录写库内 `schema_migrations` 表（name / applied_at / elapsed_ms / status / message）。
  修复前的成功记录不可信，不能直接用来跳过，也不能在未检查脚本和数据的情况下强制重跑。
- **失败即停**：任一脚本失败立即中止并汇报进度，不会在残缺 schema 上继续跑。修复后重跑同一命令即可。
- **未登记脚本拒绝运行**：目录里有 `migrate_*.py` 但不在 `ORDER` 里时，runner 以 exit 2 退出并列出文件名。
  这是为了防止新脚本被悄悄遗忘——加进 `ORDER` 时请在 PR 里说明依赖理由。
- **双方言**：`schema_migrations` 的 upsert 对 MySQL 用 `ON DUPLICATE KEY UPDATE`、
  SQLite 用 `ON CONFLICT(name)`，测试与部分部署走 SQLite 不会语法错误。

### runner 的验收口径

在一键全空库上从零执行应满足：

1. `run_migrations.py` 一次跑通 14 个，退出码 0；
2. 立即重跑，14 个全部跳过，退出码 0；
3. `--force` 重跑 14 个仍全部成功，且不产生重复数据；
4. 用隔离测试库验证应用和回填结果；旧版 runner 的测试结果不能作为迁移成功的证据。

将来若走 Plan A（真版本链），必须重新核实基线；旧 `schema_migrations` 记录不能直接作为版本依据。

## 新增迁移的规范

- **建新表**：模型中新建表后，存量生产库需要显式迁移；只有全新空库可使用空库初始化命令。
- **改已有表 / 回填数据**：新建 `scripts/migrations/migrate_<feature>.py`，必须满足：
  - 幂等：先用 `inspect` 或 `column_exists(table, column)` 判断再执行；
  - docstring 写清用法与目的（参照现有脚本的格式）；
  - 提供 `main()` 或 `migrate()` 入口（runner 两种都认）；
  - **登记进 `run_migrations.py` 的 `ORDER`** 并说明依赖理由——不登记则 runner 拒绝运行；
  - 只写 MySQL 兼容 DDL（SQLite 下 `ensure_schema_compat` 的告警是预期行为，见「已知约束」）。
- **不要**把永久业务逻辑堆进 `ensure_schema_compat` 的硬编码列表；那里只放「启动自愈」级别的兼容补列。

## 已知约束

- 启动时不再自动修改既有金额列类型：旧库的金额精度不会因此自动升级。升级前应在隔离环境检查金额列类型、可空性、默认值和数据范围，备份并验证后再制定显式迁移，禁止直接照搬不保留列属性的 `MODIFY COLUMN`。
- 上线检查 `scripts/verify/go_live_check.py --tenant <店铺标识>` 会只读核对模型所需表、列，以及 MySQL 精确数值字段的精度和小数位；发现不匹配时阻断检查。它不核验索引、约束、列默认值、数据范围或迁移回填结果，不能代替完整迁移验收。
- 开发和样板模式的 `ensure_schema_compat` 仍会自动尝试补列和建表，且部分失败只记录日志；不要将这两种模式连接到生产库。SQLite 下部分 MySQL 方言补列语句可能产生告警。
- 老库升级时 `scripts/migrations` 需按功能顺序执行；个别历史脚本未逐条验证幂等，正式跑前务必在 staging 验证。

## 后续正规化（Plan A，尚未做）

把 `ensure_schema_compat` + `scripts/migrations` 归并进真正的版本链需要：
1. `create_app` 不再无条件 `create_all`；
2. 存量库基线化到版本链；
3. 定义升级顺序、回滚与数据校验。
这是独立工程，不在当前交付路径上。
