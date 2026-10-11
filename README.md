# 项目进展与业务价值说明

最后更新：2026-10-06

## 一句话定位

云购商城是面向中小电商商家的多租户智能客服与经营自动化系统。它把顾客商城、订单交易、AI 客服、人工客服和老板经营看板放在一条数据链路中，目标是减少重复人工、提高咨询后的成交机会，并让经营风险形成明确待办。

## 效果演示

[观看演示视频](demo/demo.mp4)

当前是一个 Monorepo 项目，不是两个互不相关的项目：

```text
顾客商城 mall/
      │ 商品、咨询、下单、售后
      ▼
Flask 业务后端 flask_shop/
      │ 同一套租户、商品、订单、客服与审计数据
      ▼
商家后台 vue_shop/
```

## 当前阶段

当前达到“可交付商业演示基线”，可以向老板完整演示业务闭环，也可以在本机或测试服务器进行部署验收；尚不能宣称已经满足任意客户的正式公网生产上线要求，剩余事项统一记录在 [TODO.md](TODO.md)。

| 能力 | 当前状态 | 能解决的业务问题 |
| --- | --- | --- |
| 多租户与角色权限 | 已完成并有隔离测试 | 不同商家、员工和顾客不能互相读取业务数据 |
| 商品、SKU、库存、运费 | 已完成基础闭环 | 商家维护商品，顾客查看并下单，库存随订单扣减 |
| 商城商品实时同步 | 已完成基础能力 | 商城首次进入、切回窗口和轮询会自动拉取最新商品、主图、库存和上下架状态，不必手动刷新 |
| 订单、人工确认收款、发货、退款 | 已完成基础状态机 | 适合没有官方支付接口的小商家先进行私有化交付 |
| AI 导购与意图识别 | 已完成 | 回答商品、付款、订单和售后问题，并给出业务入口 |
| 客服响应速度优化 | 已完成第一版 | 短问、单一高置信意图直接走规则，跳过无关 Agent 和不必要的远程模型调用；复杂问题仍可使用 Agnes/OpenRouter 润色 |
| 人工客服中心 | 已完成 | AI 转人工、排队、接管、回复、结束、评价形成闭环 |
| 完整对话历史 | 已完成 | AI、顾客、人工客服和系统消息统一落库；商城打开客服页会回放当前会话，刷新后仍能看到完整时间线 |
| 导购长期记忆 | 已完成基础版 | 按租户隔离，登录顾客跨会话保存预算、品类关键词、尺码、颜色、最近商品和最近对话；匿名顾客按会话保存 |
| AI 与人工防抢答 | 已完成 | 会话排队或人工接管后，AI 不再抢答 |
| 店铺知识库与引用 | 已完成 | 商家维护付款、配送、售后和 FAQ；顾客能看到 AI 回答依据 |
| 知识缺失保护 | 已完成 | 政策问题没有可信知识时不编造，自动进入人工客服队列 |
| 客服辅助成交归因 | 已完成 | 订单显式记录咨询会话号，可统计客服辅助订单和成交额 |
| 老板经营驾驶舱 | 已完成第一版 | 查看客服价值、估算节省工时、满意度和当天优先待办 |
| AI 自动上架 | 已完成基础闭环 | 从商品入口一键生成内容和主图、保存资源并同步上架；手动素材与质检收进高级模式 |
| Agnes 图片生成并应用商品主图 | 已完成受控闭环 | 后台生成主图后可保存到本店资源目录，确认后回填商品并立即上架到商城前台 |
| 一键素材自动上架 | 已完成基础闭环 | 演示店可自动创建新商品，再生成内容、主图、保存资源并上架；离开页面后任务继续执行，返回时自动恢复运行状态、进度和结果，无需再次点击开始 |
| Agnes 文本、图片、视频模型 | 服务端已接入 | 当前商家主流程只开放文本与商品生图；尚未形成发布闭环的视频能力不在普通菜单展示 |
| 审计与可观测性 | 已完成基础能力 | 关键人工操作、自动化运行和 Agent 调用可以追踪 |
| 生产安全基线 | 已完成第一版 | 生产配置 fail-closed 校验、持久化登录防爆破、安全响应头和后台风险告警已接入 |
| 标准业务演示数据 | 已完成 | 没有真实店铺也能完成交付演示，且明确标记为演示数据 |
| 正式租户交付初始化 | 已完成命令行闭环 | 不改代码即可创建客户店铺并导入员工、商品库存和历史订单 |

## 老板现在能看到什么

商家后台已收敛为 7 个一级入口：`经营首页`、`订单`、`商品`、`客服`、`知识库`、`员工与权限`、`店铺设置`。添加商品从商品列表进入；分类参数、细粒度角色菜单与动作权限保留底层页面但不占用普通商家的导航。

广告 ROI、人工竞品记录、估算财务三表和 Agnes 短视频暂不进入普通商家操作路径。底层代码和接口暂时保留，等真实平台数据或发布闭环具备后再决定恢复，不把实验能力包装成正式业务能力。

经营首页 `/data_list` 当前直接回答：

- 近 30 天客服辅助了多少订单和已支付成交额。
- AI 独立解决了多少会话，转人工多少。
- 按配置口径估算节省了多少客服工时。
- 人工首次响应速度、满意度、待接待和处理中会话。
- 今天最需要优先处理的付款申报、人工排队、发货、售后和低库存事项。
- 近 7 日下单量、成交额及当前订单状态分布。

客服辅助成交只统计订单中的 `consultation_session_id`，不会把时间接近的订单猜测为 AI 成交。

估算节省工时的默认计算方法：

```text
估算节省工时 = AI 独立解决会话数 × SUPPORT_BASELINE_MINUTES ÷ 60
```

默认每个会话按 6 分钟估算，可通过环境变量调整。它是经营估算，不是财务凭证。

## 智能客服业务闭环

```text
顾客提问
  ↓
意图识别、风险判断与租户知识检索
  ├─ 命中已发布知识 → AI 回答 + 展示引用依据
  ├─ 普通导购问题 → 推荐商品/订单入口
  └─ 政策知识未命中、售后、风险或主动要求人工
           ↓
       人工客服队列
           ↓
     客服接管、回复、结束
           ↓
       顾客满意度评价
           ↓
订单创建时记录会话号 → 老板驾驶舱统计辅助成交
```

## 本阶段客服可用性修复（2026-10-04）

本阶段针对“回复慢、刷新丢历史、没有长期记忆、意图命中率不透明”完成了可验证的基础修复：

1. **响应链路**：短文本且只有一个高置信规则命中时，不调用远程意图模型；问候、付款、物流、订单和短商品问答直接规则回复；普通商品检索不再默认查询促销和订单。复杂问题仍保留模型增强，并可用 `AGENTS_INTENT_ALWAYS_LLM=1`、`AGENTS_CS_ALWAYS_LLM=1` 强制开启。
2. **历史回放**：`SupportConversation` 与 `SupportMessage` 统一保存顾客、AI、人工客服、系统消息；商城首次打开或刷新时调用 `/api/agents/support/session/{session_id}/messages/` 回放，轮询只追加新消息。
3. **长期记忆**：新增 `t_agent_memories`，登录顾客使用 `customer:{id}` 跨会话复用，匿名顾客使用 `session:{session_id}` 隔离；保存结构化偏好、最近 8 轮对话、最近商品和最近意图，不依赖 Python 进程内字典。
4. **意图透明度**：意图结果保留规则命中、置信度、是否使用 LLM；新增男装电商 JSONL 评测集和脚本，输出 accuracy、每意图 precision/recall 与混淆矩阵。当前 38 条样本的规则基线为 **accuracy 100%**，这不是线上命中率承诺，必须用脱敏真实会话持续扩充评测集。

相关验证命令：

```powershell
cd flask_shop
python scripts/verify/eval_intents.py
python -m pytest -q tests/test_agent_memory_and_history.py tests/test_support_center.py tests/test_store_knowledge.py tests/test_agent_guide_actions.py
```

当前持久化记忆是结构化基础版，不包含向量检索或自动摘要压缩；首次部署已有数据库时执行 `python scripts/migrations/migrate_agent_memory.py`，新开发库会由 `create_all()` 自动建表。

## 客服四项修复的实现索引

下面是本阶段功能与代码入口的对应关系，便于交付、排查和后续替换实现。

| 功能 | 主要实现 | 数据/API/配置 | 验证入口 |
| --- | --- | --- | --- |
| 意图识别与快速路径 | `flask_shop/flask_shop/agents/intent_agent.py`：`IntentAgent.INTENT_RULES` 负责规则命中，`_should_refine()` 决定是否调用远程模型；`flask_shop/flask_shop/agents/cs_agent.py`：`_should_polish()` 决定是否进行回复润色 | 返回 `data.intent.intent`、`confidence`、`raw_hits`、`llm.used`；环境变量 `AGENTS_INTENT_ALWAYS_LLM`、`AGENTS_CS_ALWAYS_LLM` 可强制启用 LLM | `flask_shop/scripts/verify/eval_intents.py`、`flask_shop/data/evals/menswear_intents.jsonl` |
| 无关 Agent 跳过 | `flask_shop/flask_shop/agents/orchestrator.py`：`run_chat()` 按意图分支；只有用户明确提到优惠、包邮、凑单等才运行促销，明确买/下单/付款才运行订单上下文 | 返回 `data.agents_ran` 和 `data.trace`，可查看本次实际运行了哪些 Agent | `tests/test_agent_guide_actions.py`、全量 `pytest` |
| 对话历史持久化 | `flask_shop/flask_shop/agents/support.py`：`ensure_conversation()`、`append_message()`、`persist_agent_turn()`；模型位于 `models.py` 的 `SupportConversation`、`SupportMessage` | 顾客、AI、staff、system 使用同一会话时间线；商城接口 `GET /api/agents/support/session/{session_id}/messages/`，支持 `after_id` 增量读取 | `tests/test_support_center.py`；前端 `mall/src/components/AgentPanel.vue` 的 `loadConversationHistory()` 和 `pollSupportMessages()` |
| 长期记忆 | `flask_shop/flask_shop/agents/support.py`：`get_memory_context()`、`save_memory_turn()`、`_extract_preferences()`；模型为 `models.py` 的 `AgentMemory` | 表 `t_agent_memories`；`customer:{id}` 跨会话，`session:{session_id}` 匿名隔离；保存 `preferences_json`、`recent_turns_json`、`last_products_json`、`last_intent_json` | `tests/test_agent_memory_and_history.py`；已有库执行 `scripts/migrations/migrate_agent_memory.py` |
| 记忆注入回复 | `flask_shop/flask_shop/agents/views.py` 在聊天请求读取持久化记忆，`orchestrator.run_chat(..., memory=...)` 写入上下文，`cs_agent.py` 将 `ctx.memory` 放入模型上下文 | 返回 `data.memory.turn_count`、`preferences`、`updated_at`；记忆读取失败不会阻断客服主回复 | 客服专项测试、全量 `pytest` |
| 商城刷新恢复 | `mall/src/components/AgentPanel.vue` 首次挂载读取 `localStorage.agent_session_id`，再请求历史；消息按 `customer → user`、`ai → assistant` 映射，并恢复引用信息 | 不依赖浏览器临时消息数组；客服状态由接口中的 conversation 同步 | `mall` 生产构建；接口回归见 `tests/test_support_center.py` |

### 一次请求的实际顺序

```text
POST /api/agents/chat/
  → 解析租户、顾客和 session_id
  → 检查是否已有人工 waiting/active（有则只入队，不调用 AI）
  → 读取 AgentMemory 与进程内短会话上下文
  → IntentAgent 规则识别（必要时才远程 LLM 增强）
  → Orchestrator 按意图调用商品、订单、促销、风控等 Agent
  → CustomerServiceAgent 规则回复（复杂问题才远程润色）
  → 返回商品、动作、引用、记忆摘要和客服状态
  → persist_agent_turn() 写入 SupportConversation/SupportMessage
  → save_memory_turn() 更新 AgentMemory
```

### 当前实现边界

- “长期记忆”是数据库中的结构化偏好与最近对话，不是向量数据库，也不是无限期保存全部聊天原文。
- “100%”只表示当前 38 条固定评测样本的规则基线结果，不能代表真实用户、换品类或换平台后的线上准确率。
- 响应速度优化减少了不必要的远程调用，但复杂问题仍受 Agnes/OpenRouter 网络、模型排队和超时影响；真实 p50/p95 需要在目标服务器测量。
- 历史接口已做租户和顾客会话校验；正式多节点部署前仍需按 `TODO.md` 将进程内短会话和后台任务迁移到共享缓存/持久化队列。

## 标准演示环境

演示数据包括 4 个顾客、6 笔不同状态订单、6 个 AI 会话、3 个人工客服案例、4 条店铺知识、广告记录和低库存场景。所有生成记录均标记为 `demo`，页面会显示“演示数据”，不能作为真实业绩对外宣传。

在 `flask_shop/` 目录执行：

```powershell
python scripts/seeds/seed_shop.py
python scripts/migrations/migrate_support_center.py
python scripts/migrations/migrate_owner_dashboard.py
python scripts/migrations/migrate_tenant_onboarding.py
python scripts/migrations/migrate_store_knowledge.py
python scripts/migrations/migrate_security_hardening.py
python scripts/seeds/seed_business_demo.py
```

`seed_business_demo.py` 是幂等脚本，可重复运行以刷新标准演示场景，不会重复堆积同一批业务数据。

演示账号：

```text
租户：demo
商家账号：admin
商家密码：123456
顾客登录：合法手机号 + 开发验证码 123456
```

默认密码与固定验证码仅允许本地演示，正式环境必须关闭。

## 正式客户初始化

系统使用租户的 `data_mode` 显式区分 `demo` 和 `live`。正式租户不能使用 `demo` 或 `demo-` 开头的团队标识，历史导入订单也不会被误算为客服辅助成交。

在 `flask_shop/` 目录创建正式租户：

```powershell
$env:FLASK_APP = "manager:app"
$env:TENANT_ADMIN_PASSWORD = "客户提供的强密码"
python -m flask tenant create `
  --slug customer-shop `
  --name "客户店铺名称" `
  --admin-name owner `
  --contact-phone "客户联系电话" `
  --freight-fee 8 `
  --free-shipping-amount 99
```

可填写模板位于 `flask_shop/data/onboarding_templates/`，包含只有表头的独立 CSV，以及带 `field_guide` 字段示例页的 Excel 工作簿；模板本身不会导入示例账号或假订单。填写后先预演，确认错误报告为空再正式导入：

```powershell
python -m flask tenant import-data `
  --slug customer-shop `
  --file data/onboarding_templates/onboarding.xlsx `
  --kind all `
  --dry-run

python -m flask tenant import-data `
  --slug customer-shop `
  --file data/onboarding_templates/onboarding.xlsx `
  --kind all

python -m flask tenant inspect --slug customer-shop
```

也可以用 `--kind products`、`staff` 或 `orders` 分别导入 CSV。错误行不会写入，命令会生成 `*.errors.csv`，其中包含行号、原因和原始数据。

演示数据清理默认只预览数量，并拒绝作用于 `live` 租户：

```powershell
python -m flask tenant purge-demo-data --slug demo
python -m flask tenant purge-demo-data --slug demo --execute --confirm demo
```

## 本地启动

### 1. API

```powershell
cd flask_shop
python run_dev_api.py
```

地址：`http://127.0.0.1:5000`  
健康检查：`http://127.0.0.1:5000/health/`  
Agent 检查：`http://127.0.0.1:5000/api/agents/health/`

### 2. 商家后台

```powershell
cd vue_shop
npm ci
npm run serve
```

默认入口：`http://127.0.0.1:8080/admin/`  
经营驾驶舱：`/admin/data_list`  
客服工作台：`/admin/customer_service`
客服知识库：`/admin/knowledge_base`

### 3. 顾客商城

```powershell
cd mall
npm ci
npm run dev
```

默认入口：`http://127.0.0.1:5173/`  
导购客服：`http://127.0.0.1:5173/agent`

## 生产部署基线

仓库保留 `deploy/` 中的 Docker、Nginx、Windows 启动、健康检查、数据库备份与恢复脚本。正式交付时必须通过环境变量配置，不允许把客户域名、数据库密码或模型密钥写进代码。

最低生产配置包括：

- 长度至少 32 位的随机 `SECRET_KEY`。
- 明确的 `CORS_ORIGINS` 或同域私有化反向代理。
- `ALLOW_MOCK_PAY=0`。
- `SMS_DEV_MODE=0` 并配置真实短信服务。
- `PUBLIC_BASE_URL` 指向客户域名或私有网络地址。
- MySQL 持久化、定期备份和已验证的恢复流程。
- HTTPS 证书、反向代理、日志和健康检查。
- `LOGIN_ACCOUNT_FAILURE_LIMIT`、`LOGIN_IP_FAILURE_LIMIT`、`LOGIN_LOCK_MINUTES` 保持安全阈值；登录失败记录写入 `t_login_throttle`，多进程部署仍生效。
- 生产短信不能使用 `console`，`SMS_PROVIDER=http` 时必须配置 `SMS_HTTP_URL`。
- Docker Compose 默认使用 `FLASK_CONFIG=product`、`SMS_DEV_MODE=0`；不要依赖默认值承载真实配置。

没有域名不影响本地演示和私有网络验收；正式公网交付时再绑定客户域名与 HTTPS。

## 验证命令

```powershell
cd flask_shop
python -m pytest -q
python -m compileall -q flask_shop scripts tests

cd ..\vue_shop
npm run build

cd ..\mall
npm run build

cd ..
git diff --check
```

当前已验证：

- 后端 87 个自动化测试全部通过，包含正式租户初始化、数据导入、店铺知识租户隔离、引用返回、知识未命中转人工、登录防爆破、生产配置校验、演示清理保护、经营驾驶舱和客服订单归因。
- 商家后台与商城生产构建通过。
- API 健康检查不再返回环境名，并统一返回 `nosniff`、`DENY`、Referrer-Policy 和 Permissions-Policy 安全响应头。
- 客服知识库已在 1440 和 390 像素视口完成真实登录、接口数据、表格、编辑对话框与无横向溢出验收。
- 商城客服已在 390 像素视口完成真实知识命中、引用展示和状态栏验收。
- 经营驾驶舱已在 1440、768、390 像素三档视口完成真实登录、接口数据、图表渲染、无横向溢出和无前端运行错误验收。
- 经营驾驶舱遵循现有 Vue 3、Element Plus 和 Flask 模块化单体规范。

## 关键目录

| 路径 | 作用 |
| --- | --- |
| `flask_shop/flask_shop/` | Flask 领域模型、接口、客服和自动化业务 |
| `flask_shop/tests/` | 多租户、交易、客服、自动化和商业加固测试 |
| `flask_shop/scripts/migrations/` | 既有数据库增量迁移 |
| `flask_shop/scripts/seeds/` | 基础店铺与标准演示数据 |
| `vue_shop/` | 商家后台与老板经营驾驶舱 |
| `mall/` | 顾客商城和导购客服 |
| `deploy/` | 容器、反向代理、备份和本机部署脚本 |

## 本阶段更新记录

2026-09-29：

- 增加订单与客服会话的显式归因字段。
- 增加老板经营驾驶舱的客服价值和优先待办指标。
- 增加幂等标准业务演示数据脚本。
- 增加经营指标和订单归因自动化测试。
- 增加正式租户创建、CSV/XLSX 初始化导入、错误报告与演示数据安全清理命令。
- 增加租户 `demo/live` 显式数据模式，并完成独立空库交付演练。
- 增加租户级店铺知识库、后台 CRUD、CSV 模板与逐行导入错误反馈。
- 增加 AI 回答引用依据；付款、配送、售后等政策问题未命中时自动转人工。
- 增加知识库租户隔离、草稿隔离、引用、未命中转人工和导入审计测试。
- 增加持久化账户/IP 登录防爆破、生产配置 fail-closed 校验、安全响应头和后台安全告警。
- 文档压缩为本说明和 `TODO.md` 两份，避免历史方案与当前实现冲突。

2026-10-04：

- 完成导购客服四项可用性修复：规则快速路径、无关 Agent 跳过、商城完整历史回放和数据库持久化长期记忆。
- 增加 `AgentMemory` 模型、幂等迁移脚本、偏好提取测试和意图评测脚本；修复评测脚本直接运行时的模块路径问题。
- 后端编译、全量测试（当前 87 个用例）、商城生产构建和商家后台生产构建均通过；构建保留既有非阻断警告。

2026-10-06：

- 自动上架页面新增任务状态恢复：进入页面时从 `t_automation_runs` 查询本租户正在运行的任务，没有运行任务则展示最近一次结果。
- 运行中的任务会自动恢复每 2 秒轮询，离开其他页面再返回时仍显示运行中、正在结束、完成进度和逐商品结果。
- 新增 `GET /api/automation/creative/auto/current/`，重复点击开始遇到已有任务时直接恢复已有任务，不会要求重新启动。
