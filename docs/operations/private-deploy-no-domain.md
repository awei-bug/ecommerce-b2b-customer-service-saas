# 无服务器、无域名的部署手册

> 目标：**不买服务器、不买域名**，把整套系统跑起来。验证状态见文末。

适用场景与对应方案：

| 场景 | 方案 | 入口 |
|---|---|---|
| A. 本机单机（Windows） | 单入口服务（waitress） | `deploy\win\start_sample_shop.bat` |
| B. 一台无域名的 Linux VPS | docker compose + nginx（HTTP/IP 访问） | `deploy/docker-compose.yml` |
| C. 店内有几台电脑共用 | 场景 A + 监听内网 IP | 改 `SAMPLE_HOST` |

## 场景 A：本机单机（Windows，推荐先跑这个）

一条命令把商城 + 后台 + API 全部跑在一个端口：

```
deploy\win\start_sample_shop.bat
```

启动后：

- 商城  http://127.0.0.1:18080/
- 后台  http://127.0.0.1:18080/admin/
- 健康  http://127.0.0.1:18080/health/
- 店长  团队 `demo` / 账号 `admin` / 密码 `123456`
- 顾客  任意手机号 + 页面验证码（样板模式固定验证码 123456）

行为说明（已实测验证）：
- 首次启动自动建库、灌入演示数据（商品 8 个 + SKU + 运费模板）。
- 前端 dist 缺失时自动构建；后台 dist 会校验 `/admin/` 基路径，不对会重建。
- 数据库优先用 `flask_shop/.env` 里的 MySQL；没有则用本地 SQLite 样板库。

### 让店内其他设备也能访问（场景 C）

默认只监听 `127.0.0.1`（仅本机）。要让局域网内其他电脑访问：

```
set SAMPLE_HOST=0.0.0.0
set SAMPLE_PORT=18080
flask_shop\.venv\Scripts\python.exe deploy\win\sample_shop_server.py
```

其他设备用 `http://<这台电脑的局域网IP>:18080/` 访问。
**注意**：跨设备访问时，`CORS_ORIGINS` 需要包含该访问地址（`deploy/.env.prod` 里设置，或临时用 `set CORS_ORIGINS=http://<IP>:18080`）。

## 场景 B：一台无域名的 Linux VPS（IP 访问）

目标：`http://<服务器IP>` 直接访问商城，`http://<服务器IP>/admin/` 访问后台。

1. 在服务器装好 Docker + Docker Compose。
2. 仓库根目录：
   ```
   cp deploy/.env.prod.example deploy/.env.prod   # 编辑：SECRET_KEY、数据库密码等
   docker compose -f deploy/docker-compose.yml --env-file deploy/.env.prod build api
   docker compose -f deploy/docker-compose.yml --env-file deploy/.env.prod up -d mysql
   ```
3. 等待 MySQL 健康检查通过。仅对确定为空的**新库**，将下方库名替换为 `.env.prod` 中的 `MYSQL_DB`，核对实例和库名后显式建表：
   ```
   docker compose -f deploy/docker-compose.yml --env-file deploy/.env.prod run --rm --no-deps api python scripts/migrations/init_empty_schema.py --confirm-database flask_shop_saas
   ```
   不要对存量库运行此命令；建表过程中禁止其他进程并发改库。若执行中断，可能留下部分表，需先审查，不能盲目重试。存量库先备份并按数据库迁移文档制定升级方案。
4. 启动 `docker compose -f deploy/docker-compose.yml --env-file deploy/.env.prod up -d`。生产 API 会只读检查结构，不会自动补表或补列。为真实商家创建正式租户，例如在 API 启动后执行：
   ```
   docker compose -f deploy/docker-compose.yml --env-file deploy/.env.prod exec api flask --app wsgi tenant create --slug my-shop --name 我的店铺
   ```
   按提示交互输入强管理员密码，避免把密码写入命令历史；不要使用演示种子脚本初始化真实商家。实际命令和后续导入仍需在目标服务器验证。
5. 浏览器打开 `http://<服务器IP>:18080/`（HTTP 发布端口默认 18080，见 `.env.prod` 的 `HTTP_PUBLISH_PORT`）。

说明：
- Compose 默认只加载 `deploy/nginx/conf.d/default.conf`，避免多个站点同时监听 80 时路由与健康检查选错；通过 `NGINX_SITE_CONFIG` 可选择另一份经过核验的站点配置。
- 上传目录经 `shop_uploads` 卷在 api 与 nginx 间共享，图片走 nginx 直出。
- nginx 健康检查 `http://127.0.0.1/healthz` → API `/health/`，compose 里已配。
- `/health/` 和 `/healthz` 只验证 API 进程响应，不验证数据库或业务可用性；生产环境不公开 `/metrics/` 的跨租户统计，数据库与业务告警需使用受保护的监控方案。
- 审计使用独立连接池，每个 API 进程最多额外占用 2 个数据库连接，池满等待约 1 秒后记录失败；容量规划需计入进程数，并为 `audit write failed` 配置告警。审计是 best-effort，不能替代可靠的合规审计；上述行为尚需在隔离 MySQL 和目标服务器实测。
- **该路径尚未在真实服务器上实测**；本机 Docker CLI 可解析 Compose 配置，但当前 Docker 引擎不可用，尚未验证容器内 Nginx 配置或端到端路由。上真实服务器后需按「文末验证清单」过一遍。

## 以后有了域名 + 证书

1. 将 `deploy/nginx/conf.d/default.ssl.conf.example` 复制为独立配置，按域名及证书调整，并在 `.env.prod` 中用 `NGINX_SITE_CONFIG` 指定相对于 `deploy` 的配置路径；放入证书（`deploy/certs/fullchain.pem` / `privkey.pem`）。确认配置仅由一个站点文件监听对应端口。
2. `.env.prod` 设置 `PUBLIC_BASE_URL=https://你的域名`、`CORS_ORIGINS=https://你的域名`。
3. 若用 Docker，重新 `up -d --build`。Windows 单机版改 `PUBLIC_BASE_URL` 后重启即可。

## 验证清单（无域名上线前逐项过）

基础配置检查可在目标环境运行 `python scripts/verify/go_live_check.py --tenant <店铺标识>`（在 `flask_shop` 目录执行）。检查尊重现有环境变量及 `DATABASE_URL`，生产模式必须明确指定店铺；此检查不自动建表或启动关单任务，也不会输出数据库密码，但仅覆盖部分条件，不能替代以下上线验收。

检查会阻断所选店铺员工仍使用已知演示密码 `123456` 的情况；这不是完整弱密码审计，仍需逐一核查所有员工凭据和账户权限。密码哈希验证耗时与员工数量成正比，应在维护窗口执行。

微信直连支付的发起、回调状态更新和主动查单补偿目前被安全闸门禁用；不得用于正式收款。若已有微信交易，需在商户平台人工核对处理，不能仅凭本地订单状态判断支付结果。完整校验与真实渠道验收完成前不得移除闸门。

客户端地址默认只取实际连接地址，不信任请求自带的 `X-Forwarded-For`。Compose 的 API 配置 `TRUST_PROXY_HOPS=1`，只适用于 API 未对外开放、所有流量都经过本项目 Nginx 的部署；Nginx 会覆盖而不是追加该请求头。如果 API 可被其他客户端直接访问，必须关闭代理信任并限制网络访问，否则客户端仍可伪造地址。使用 CDN 或额外负载均衡时，先在入口配置可信代理地址并验证真实客户端地址，不能直接沿用单层代理假设。

平台租户管理接口默认关闭（`PLATFORM_API_ENABLED=0`），正式开店可使用上面的 CLI。确需通过 `/api/p/tenants/` 接口管理租户时，先在网关限制为可信管理网络并配置限流、审计和密钥轮换，再设置 `PLATFORM_API_ENABLED=1` 和强随机平台密钥；应用层开关不是网络隔离，也不能代替这些措施。上线检查会提示该接口已启用。

短信发送限流记录在数据库中，默认同一手机号跨店铺 60 秒一次、同一来源地址每 60 秒最多 10 次；网关失败也消耗本次冷却。内存限流仍然只是单进程的辅助保护，不能代替网关侧配额、数据库多进程限流及目标环境验证。

进程内限流桶设有容量上限，按需清理过期桶；达到上限时新来源会暂时收到 503，而不是绕过限流。高基数攻击仍可能影响可用性，需在网关限制来源并监控 503；重启或多进程不会共享这些计数。

新付款截图保存在非静态私有目录，Compose 使用独立 `shop_pay_proofs` 卷，仅 API 挂载；读取时仍校验订单顾客或商家订单读取权限。旧截图仍在上传卷的 `租户ID/pay_proof` 下，仅供鉴权接口兼容读取：部署时必须确认所有 Nginx、CDN、对象存储及其他静态服务均拒绝直接访问该目录，并清理曾公开缓存。应用内拦截无法保护绕过应用的静态服务器，旧文件仍需规划迁移并在目标环境实测。

新截图限制文件大小和像素数，检查内容格式与扩展名一致并解码首帧；这不是病毒扫描，也不会清除元数据。部署需安装后端依赖中的 Pillow，仍需确定截图保留与删除策略。

旧截图可按店铺迁移：先备份数据库、上传卷与私有卷并验证备份；在维护窗口停止应用写入，确认进程使用正确数据库和两个存储目录。在 `flask_shop` 目录运行 `python scripts/verify/migrate_pay_proofs.py --tenant <店铺标识>` 预演；无异常后可追加 `--execute --confirm-database <数据库名>` 执行。工具逐条复制并比对内容，条件更新订单引用，保留原文件；中断或失败可能留下私有目录中的未引用副本，需要核对后处理。执行后检查顾客和员工授权读取、备份恢复、其他静态服务及 CDN 缓存；不要直接批量删除旧文件，须先核实所有引用和备份并制定单独的清理方案。该工具与暂停执行的数据库结构迁移 runner 无关，尚需目标环境演练。

- [ ] 商城首页能打开，商品有图可加购。
- [ ] 后台登录、改价/上下架、接单发货全流程可用。
- [ ] AI 客服能答、能转人工。
- [ ] 付款走「人工确认收款」闭环（无支付牌照时默认模式）。
- [ ] 上传商品图后，图片 URL 能稳定访问（nginx 直出路径正确）。
- [ ] 重启服务后数据还在（MySQL 卷 / SQLite 文件持久化）。
- [ ] 登录失败 5 次会被锁定（防爆破）。
- [ ] 关闭 `ALLOW_MOCK_PAY`、`SMS_DEV_MODE` 后，固定验证码和模拟支付不可用。
- [ ] 恢复演练跑过一遍，结论为全 PASS（见下节）。

## 备份与恢复演练

上线前必须做一次**有记录**的恢复演练——"脚本存在"不算，要能证明这份备份真能救回来。

Linux 生产备份可运行 `bash deploy/backup_all.sh`：默认通过 `MYSQL_HOST`、`MYSQL_PORT` 和本机 `mysqldump` 连接；只有显式设置 `MYSQL_BACKUP_METHOD=docker` 才使用 `MYSQL_CONTAINER` 内的数据库，避免误备份同机的其他实例。上传文件与私有付款截图默认随该方式从本机目录或 `shop_api` 容器读取；可用 `UPLOAD_BACKUP_METHOD`、`UPLOAD_BACKUP_CONTAINER`、`UPLOAD_BACKUP_SOURCE` 和 `PROOF_BACKUP_SOURCE` 显式指定，必须确认指向实际实例和卷。数据库、上传包、私有截图包均成功才算完成；目录缺失或打包失败会报错，已生成的部分备份不代表全量备份成功。三者不保证同一时刻的快照，需结合业务停写窗口或其他一致性方案；文件包在两种模式下目录前缀不同，恢复时先查看包内容，分别恢复上传卷及私有卷并核验权限。

Windows 的 `backup_mysql_local.py` 使用 `MYSQL_*` 变量，不解析 `DATABASE_URL`，不等同于上述生产 `mysqldump` 流程，也不能据此声称已验证生产备份。若应用使用 `DATABASE_URL`，运行前必须确保 `MYSQL_*` 指向同一个实例和库。本地脚本会将表数据加载到内存，且未验证跨表一致性，主要用于开发或隔离演练，不应作为正式环境的唯一备份。

```
cd flask_shop
python ..\deploy\win\backup_mysql_local.py          # 先打一份新备份
python scripts\verify\rehearse_restore.py           # 备份 → 恢复到临时库 → 逐表核对
```

仅使用可信备份，并在与正式数据库隔离的 MySQL 实例中演练：SQL 文件本身可能包含跨库或破坏性操作，脚本不能将不可信 SQL 安全沙箱化。演练读取当前应用配置指向的源库进行对比，因此应先在隔离实例中准备源库副本，并将应用数据库配置指向该副本，**不要直接用正式库作为演练实例**。

脚本做四件事：

1. 取最新备份（或 `--backup 指定文件`）；
2. 恢复到随机命名的新临时库，不覆盖任何已有库；`RESTORE_DB` 不再支持；
3. 逐表比对当前源库与恢复库行数（不是备份时刻的快照），并对 `t_order` / `t_payments` / `t_tenants` 做数据合法性抽查
   （金额非负、状态非空、租户 slug 唯一）；
4. 检查演练前后源库副本行数是否一致；行数一致不能证明数据未被修改，期间并发写入也可能导致检查失败。

完成核对后结论写入 `deploy/backups/rehearsal-<时间戳>.json`，含逐项断言明细；前置检查或恢复异常可能提前退出而不生成报告。任一检查失败则 exit 1。

`--keep` 可保留临时库供人工排查；正常核对完成且不加该参数时删除。恢复过程异常可能留下临时库，脚本会输出其名称，须由管理员确认后手工清理。

此前文档中标注的未来日期演练记录不能作为当前验收凭据。脚本修改后尚需在隔离实例重新执行，保存备份、报告及应用级冒烟结果；仅有逐表行数和抽查不足以证明完整恢复。

> 注意：`deploy/backups/` 已被 `.gitignore` 忽略（备份含真实数据快照，不应入库）。
> 演练报告同理不入库；交付时把 `rehearsal-*.json` 随交付包单独归档。

## 已验证 vs 待验证

- **已实测（本机）**：Windows 单入口（场景 A）——建库、播种、商城/后台/API 同端口、登录、商品、顾客接口全部通过；`requirements.txt` 全新安装可导入（含补声明的 `requests`/`wechatpayv3`/`waitress`）。
- **待实测**：Docker compose（场景 B）——本机无 Docker，配置已写好但需在一台真实 VPS 上跑一遍验证清单。
