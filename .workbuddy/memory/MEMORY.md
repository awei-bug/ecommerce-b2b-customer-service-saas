# 项目长期记忆：Flask 电商 SaaS

## 项目定位
多租户 SaaS 电商操作系统（自研）。后端 Flask 模块化单体，前端两个 Vue3：
- `vue_shop/` = B 端商户后台（Vue CLI + Element Plus）
- `mall/` = C 端 PC 商城（Vite）
- `docs/saas-plan/` = 架构与落地规划文档
- `deploy/` = 容器化部署
当前进度：L0 可交易完成 + 部分 L1 可运营。

## 关键架构事实
- 多租户隔离：`tenant_id` 来自**签名的 JWT**；`login_required` 校验 header 租户与 token 一致（否则 403）。**方案2 已加集中强制**：`flask_shop/utils/tenant_query.py` 用 SQLAlchemy `before_compile` 事件，对所有 `Model.query` / `db.session.query` 在执行前自动注入 `tenant_id` 过滤（仅对带 `tenant_id` 列的模型生效）。手动 `tenant_filter`/`get_for_tenant` 仍保留为显式意图（双重过滤无害）。隔离依据：优先 `tenant_context(tenant_id=)` override，否则 `flask.g.tenant_id`。
- 鉴权：`utils/token.py`（merchant / customer / optional 装饰器）；`utils/tenant.py`（tenant_filter / get_for_tenant / require_tenant_id）。
- 支付：mock 默认（`ALLOW_MOCK_PAY`）；真微信因无商户号未端到端验证。

## 测试与 CI 约定（已建立）
- 隔离回归测试：`flask_shop/tests/`（pytest.ini + conftest + test_tenant_isolation.py），临时 SQLite，**17 例**（13 原 + 4 方案2：自动隔离/多模型统一/豁免/反向控制）。
- 运行：`cd flask_shop && .venv/Scripts/python.exe -m pytest -q`（pytest 已装进 .venv）。
- 测试用户须赋"超级管理员"角色绕过 RBAC 只读校验。
- **CI**：`.github/workflows/ci.yml`（GitHub Actions，Python 3.12，ubuntu），设 `TENANT_STRICT=1` 跑 pytest。**仓库当前无 git**——需 `git init` 并推送后 CI 才生效。
- **conftest 播种**必须用 `tenant_context(disabled=True)` 包裹：播种是跨租户初始化，否则 `TENANT_STRICT=1` 下因未绑租户报错。

## 坑（避免重复踩）
- monkeypatch 租户函数必须打**视图模块级**（`flask_shop.product.views.get_for_tenant`），因为视图用 `from ... import` 按名导入，`patch flask_shop.utils.tenant.get_for_tenant` 无效。
- `c_api` 租户缺失现返回 400（曾误返回 200，已修）。
- **before_compile 自动隔离的坑**：
  - `inspect` 在 `sqlalchemy` 顶层，不是 `sqlalchemy.orm`（导入报错）。
  - before_compile 触发时查询可能已带 LIMIT/OFFSET，直接 `query.filter()` 报 "Query.filter() being called on a Query which already has LIMIT or OFFSET applied" → 加 filter 前临时 `query._enable_assertions = False`（SQLAlchemy 2.0 编译顺序正确，WHERE 仍在 LIMIT 前）。
  - retval=True 模式返回的新 query 会再次经过 before_compile → 必须设 `query._tenant_isolated = True` 防递归/重复注入。
  - 豁免：无 `tenant_id` 列的模型（Tenant / Menu）自动不过滤；`PlatformAuditLog` 的 tenant_id 可空，平台查询 g.tenant_id=None 时不加过滤。
  - 跨租户操作（平台中台 / 迁移 / seed）用 `tenant_context(disabled=True)` 或环境变量 `TENANT_FILTER_DISABLED=1` 绕过；`TENANT_STRICT=1` 时未绑租户查租户数据直接报错（开发/CI 用）。
  - **认证顺序坑（已修）**：`utils/token.py` 的 `login_required` / `customer_login_required` / `optional_customer_login` 原本先查 `User`/`Customer`（带 tenant_id）后调 `bind_tenant`，导致 `g.tenant_id` 未绑时查租户表 → `TENANT_STRICT=1` 报错。已把 `bind_tenant(tenant)` 提前到查 `User`/`Customer` 之前。非 STRICT 模式靠 `filter_by` 显式 tenant_id 兜底，侥幸正确，但这是真实顺序缺陷。
  - `platform_api` 用 X-Platform-Key 鉴权、**不绑租户**（g.tenant_id=None）→ 自动不隔离，符合平台跨租户语义。**但若在 `TENANT_STRICT=1` 环境跑 platform_api 会报错**——STRICT 仅用于单租户测试/CI，生产/平台环境不要开。平台跨租户查询如需在 STRICT 下运行，须用 `tenant_context(disabled=True)` 包裹。

## 用户偏好（来自合作）
- 用户用中文沟通；关注"项目最大风险/问题"这类架构级判断。
- 倾向直接可执行结果（已两次让我直接动手执行方案）。
