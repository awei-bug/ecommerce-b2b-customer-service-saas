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
   docker compose -f deploy/docker-compose.yml --env-file deploy/.env.prod up -d --build
   ```
3. 浏览器打开 `http://<服务器IP>:18080/`（HTTP 发布端口默认 18080，见 `.env.prod` 的 `HTTP_PUBLISH_PORT`）。

说明：
- 站点配置是本次新增的 `deploy/nginx/conf.d/shop.conf`（HTTP、`server_name _` 接受任意 IP、代理全部 API 前缀、直接服务上传文件）。
- 上传目录经 `shop_uploads` 卷在 api 与 nginx 间共享，图片走 nginx 直出。
- nginx 健康检查 `http://127.0.0.1/healthz` → API `/health/`，compose 里已配。
- **该路径尚未在真实服务器上实测**（本机无 Docker），上真实服务器后需按「文末验证清单」过一遍。

## 以后有了域名 + 证书

1. `deploy/nginx/conf.d/shop.conf` 里取消注释的 443 server 块，改 `server_name` 为你的域名，放入证书（`deploy/certs/fullchain.pem` / `privkey.pem`）。
2. `.env.prod` 设置 `PUBLIC_BASE_URL=https://你的域名`、`CORS_ORIGINS=https://你的域名`。
3. 若用 Docker，重新 `up -d --build`。Windows 单机版改 `PUBLIC_BASE_URL` 后重启即可。

## 验证清单（无域名上线前逐项过）

- [ ] 商城首页能打开，商品有图可加购。
- [ ] 后台登录、改价/上下架、接单发货全流程可用。
- [ ] AI 客服能答、能转人工。
- [ ] 付款走「人工确认收款」闭环（无支付牌照时默认模式）。
- [ ] 上传商品图后，图片 URL 能稳定访问（nginx 直出路径正确）。
- [ ] 重启服务后数据还在（MySQL 卷 / SQLite 文件持久化）。
- [ ] 登录失败 5 次会被锁定（防爆破）。
- [ ] 关闭 `ALLOW_MOCK_PAY`、`SMS_DEV_MODE` 后，固定验证码和模拟支付不可用。

## 已验证 vs 待验证

- **已实测（本机）**：Windows 单入口（场景 A）——建库、播种、商城/后台/API 同端口、登录、商品、顾客接口全部通过；`requirements.txt` 全新安装可导入（含补声明的 `requests`/`wechatpayv3`/`waitress`）。
- **待实测**：Docker compose（场景 B）——本机无 Docker，配置已写好但需在一台真实 VPS 上跑一遍验证清单。
