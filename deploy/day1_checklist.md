# Day1 检查清单（可勾选）

> 对应《2周私有化内测冲刺清单》Day 1–2 生产最小包。  
> 仓库内 **Docker Compose + Nginx + Gunicorn** 骨架已在 `deploy/`；本清单用于你当天逐项打勾。

---

## A. 配置（必做）

- [ ] 复制 `deploy/.env.prod.example` → `deploy/.env.prod`
- [ ] 生成并填入强随机：
  - [ ] `SECRET_KEY`
  - [ ] `MYSQL_PASSWORD` / `MYSQL_ROOT_PASSWORD`
  - [ ] `PLATFORM_BOOTSTRAP_KEY`
- [ ] 确认生产安全默认：
  - [ ] `FLASK_CONFIG=product`
  - [ ] `ALLOW_MOCK_PAY=0`
  - [ ] `SMS_DEV_MODE=0`
  - [ ] `PAY_DEFAULT_CHANNEL=mock`（无商户号）
- [ ] （可选）`CORS_ORIGINS=https://你的域名`  
- [ ] `flask_shop` 生产启动走 `wsgi.py`（已校验弱 `SECRET_KEY` 会拒绝启动）

生成密钥：

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

---

## B. 本机快速验证（Windows 无 Docker 也可）

```bat
:: 1) API 类生产
deploy\win\start_api_prod.bat

:: 2) 另开终端探活
curl http://127.0.0.1:5000/health/
```

- [ ] `/health/` 返回 200  
- [ ] 用 **product** 配置时，未改 `SECRET_KEY` 应启动失败（安全）  
- [ ] 登录 `demo-a / admin_a` 成功（开发库数据）

---

## C. 前端生产构建

```bash
# Git Bash / WSL
bash deploy/build_frontends.sh
```

- [ ] 生成 `vue_shop/dist`
- [ ] 生成 `mall/dist`
- [ ] 商户后台生产 `baseURL` 为空（同域）；可用 `VUE_APP_API_BASE` 覆盖
- [ ] mall 请求 `/api/c`（Nginx 反代）

---

## D. Docker 一键（推荐 Linux 服务器）

```bash
cp deploy/.env.prod.example deploy/.env.prod
# 编辑密钥...
bash deploy/build_frontends.sh
docker compose -f deploy/docker-compose.yml --env-file deploy/.env.prod up -d --build
```

默认入口（避免占 80）：

- HTTP：`http://服务器IP:18080/`  → mall  
- 后台：`http://服务器IP:18080/admin/`  
- 健康：`http://服务器IP:18080/healthz` 与 `/health/`

- [ ] `docker compose ps` 全部 healthy  
- [ ] 浏览器打开 mall + admin  
- [ ] 登录后台成功  
- [ ] 商城能拉到商品（注意 `?tenant=demo-a`）

探活脚本：

```bash
bash deploy/healthcheck.sh
API_URL=http://127.0.0.1:5000 PUBLIC_URL=http://127.0.0.1:18080 bash deploy/healthcheck.sh
```

---

## E. Nginx 已覆盖的 API 前缀

`deploy/nginx/conf.d/default.conf` 已反代：

- 业务：`/user` `/orders` `/product` `/pay` …  
- 新增：`/dashboard` `/payments`  
- C 端/平台：`/api/`  
- 静态上传：`/static/upload/`  
- 后台：`/admin/`  
- 商城：`/`  

有证书时参考：`deploy/nginx/conf.d/default.ssl.conf.example`

---

## F. Day1 出口（今晚必须达成）

| # | 标准 | ☐ |
|---|------|---|
| 1 | 生产配置模板填完（强密钥、关 mock/SMS 开发码） | ☐ |
| 2 | API 以 **product** 模式可启动且 `/health/` 正常 | ☐ |
| 3 | 前端 **build** 成功，dist 存在 | ☐ |
| 4 | （有 Docker）Compose 拉起后 admin+mall 可打开 | ☐ |
| 5 | 记录访问 URL 与账号到内测备忘（勿用默认弱密码对外） | ☐ |

**未完成可明日继续：** 真域名 HTTPS、systemd 守护、自动备份（Day2–3）。

---

## G. 相关文件

| 文件 | 作用 |
|------|------|
| `deploy/.env.prod.example` | 生产环境变量模板 |
| `deploy/docker-compose.yml` | MySQL + API + Nginx |
| `deploy/nginx/conf.d/default.conf` | 反代与静态 |
| `deploy/build_frontends.sh` | 构建两端前端 |
| `deploy/healthcheck.sh` | 探活 |
| `deploy/win/start_api_prod.bat` | Windows 类生产 API |
| `flask_shop/wsgi.py` | Gunicorn/Waitress 入口 |
| `flask_shop/config.py` → `ProductionConfig` | DEBUG 关、mock 默认关 |

---

## H. 今天不要做

- 上 Vercel 公开站  
- 开真微信支付  
- 加新业务功能（Day1 只碰部署与配置）
