# 生产部署说明（私有化 · Day1 起）

> **Day1 勾选清单：** [day1_checklist.md](./day1_checklist.md)  
> **两周内测：** [../docs/saas-plan/2周私有化内测冲刺清单.md](../docs/saas-plan/2周私有化内测冲刺清单.md)  
> 支付：无商户号 → `ALLOW_MOCK_PAY=0`，店长使用 **标记已付款**。

## Day1 最快路径

```bat
:: Windows 类生产 API
deploy\win\start_api_prod.bat
curl http://127.0.0.1:5000/health/
```

```bash
# 构建前端 + Docker
cp deploy/.env.prod.example deploy/.env.prod   # 再编辑强密钥
bash deploy/build_frontends.sh
docker compose -f deploy/docker-compose.yml --env-file deploy/.env.prod up -d --build
# 默认 http://IP:18080/  与  http://IP:18080/admin/
bash deploy/healthcheck.sh
```

## Day2 备份 / HTTPS / 守护

见 **[day2_checklist.md](./day2_checklist.md)**。

```bat
:: Windows 本机备份（需 mysqldump 在 PATH 或设置 MYSQL_BIN）
deploy\win\backup_mysql.bat

:: 恢复到临时库演练
deploy\win\restore_mysql_test.bat deploy\backups\xxx.sql
```

```bash
bash deploy/backup_all.sh          # 库 + 上传目录
bash deploy/backup_mysql.sh
```

HTTPS 样例：`nginx/conf.d/default.ssl.conf.example`  
systemd 样例：`systemd/flask-shop-api.service.example`

---

---

## 0. 架构

```text
Internet
   │
   ▼
 Nginx :80/:443
   ├─ /            → mall 静态（C 端）
   ├─ /admin/      → vue_shop 静态（商户后台）
   ├─ /user|/orders|… → Flask API
   └─ /api/c|/api/p   → Flask API
   │
   ▼
 Gunicorn (wsgi:app) :5000
   │
   ▼
 MySQL 8
```

目录：

```text
deploy/
  docker-compose.yml
  Dockerfile.api
  gunicorn.conf.py
  .env.prod.example
  nginx/
  backup_mysql.sh
  build_frontends.sh
  certs/                 # 放置 TLS 证书（自备）
flask_shop/wsgi.py       # 生产入口
```

---

## 1. 服务器准备

- 系统：Ubuntu 22.04 LTS 或同类 Linux  
- 安装：Docker + Docker Compose 插件  
- 域名（可选）：`shop.example.com` 解析到服务器 IP  
- 安全组放行：`80`、`443`（MySQL **不要**对公网开放）

```bash
# 示例：Ubuntu
sudo apt update
sudo apt install -y docker.io docker-compose-v2
sudo usermod -aG docker $USER   # 重新登录生效
```

---

## 2. 配置环境变量

在仓库根目录：

```bash
cp deploy/.env.prod.example deploy/.env.prod
# 编辑 deploy/.env.prod
```

**必改项：**

| 变量 | 说明 |
|------|------|
| `SECRET_KEY` | 长随机串 |
| `MYSQL_PASSWORD` / `MYSQL_ROOT_PASSWORD` | 强密码 |
| `PLATFORM_BOOTSTRAP_KEY` | 开通租户用 |
| `ALLOW_MOCK_PAY=0` | 生产禁止假支付 |
| `CORS_ORIGINS` | 若前后端不同域则填写 |

生成密钥：

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

---

## 3. 前端构建与 API 地址

### 3.1 构建

```bash
bash deploy/build_frontends.sh
```

### 3.2 商户后台 API 地址

当前 `vue_shop/src/api/base.js` 默认 `http://localhost:5000`。  
**上线前**请改为与浏览器同域，例如：

```js
baseURL: '',  // 同域 Nginx 反代
// 或
baseURL: 'https://shop.example.com',
```

然后重新 `npm run build`。

`mall` 开发代理指向 5000；生产构建应请求同域 `/api/c/...`（检查 `mall` 的 `request` baseURL）。

---

## 4. 启动

```bash
cd /path/to/repo
docker compose -f deploy/docker-compose.yml --env-file deploy/.env.prod up -d --build
```

查看状态：

```bash
docker compose -f deploy/docker-compose.yml ps
docker compose -f deploy/docker-compose.yml logs -f api
curl -s http://127.0.0.1/healthz
curl -s http://127.0.0.1/health/
```

### 4.1 初始化库表与演示数据（首次）

```bash
docker exec -it shop_api python scripts/migrate_l0_ops.py
docker exec -it shop_api python scripts/migrate_l1_features.py
docker exec -it shop_api python scripts/migrate_commercial_manual_pay.py
docker exec -it shop_api python scripts/seed_tenants.py
docker exec -it shop_api python scripts/seed_rbac_roles.py --with-users
docker exec -it shop_api python scripts/seed_freight.py
docker exec -it shop_api python scripts/reset_demo_passwords.py
```

生产租户建议改密码、改付款指引，或用平台 API 开通新店。

---

## 5. HTTPS

1. 申请证书（Let’s Encrypt / 云厂商免费证书）  
2. 将 `fullchain.pem`、`privkey.pem` 放到 `deploy/certs/`  
3. 参考 `nginx/conf.d/default.ssl.conf.example` 启用 443  
4. 重载：

```bash
docker exec shop_nginx nginx -t && docker exec shop_nginx nginx -s reload
```

没有域名时，可先用 HTTP + IP 内测（勿对公网暴露无鉴权管理面）。

---

## 6. 备份

```bash
chmod +x deploy/backup_mysql.sh
# 在能访问 MySQL 的机器上：
export MYSQL_PORT=3307 MYSQL_PASSWORD='你的密码'
./deploy/backup_mysql.sh
```

建议 crontab（每天 3:15）：

```cron
15 3 * * * cd /path/to/repo && MYSQL_PASSWORD=*** ./deploy/backup_mysql.sh >> /var/log/shop_backup.log 2>&1
```

恢复示例：

```bash
gunzip -c backups/flask_shop_xxx.sql.gz | docker exec -i shop_mysql mysql -ushop -p'密码' flask_shop_saas
```

---

## 7. 上线检查清单（私有化 1 家）

- [ ] `FLASK_CONFIG=product` / `DEBUG` 关闭  
- [ ] `SECRET_KEY` 非默认  
- [ ] `ALLOW_MOCK_PAY=0`  
- [ ] `SMS_DEV_MODE=0`  
- [ ] MySQL 不对公网  
- [ ] HTTPS 或至少仅内网/VPN 访问  
- [ ] 备份脚本跑通一次  
- [ ] 店长账号改密  
- [ ] 店铺设置填写 **付款指引**  
- [ ] 走通：上架 → 顾客下单 → 标记已付款 → 发货  
- [ ] 前端 `baseURL` 指向生产  

---

## 8. 常用运维命令

```bash
# 重启 API
docker compose -f deploy/docker-compose.yml restart api

# 看日志
docker logs --tail 200 shop_api

# 进入 API 容器
docker exec -it shop_api bash

# 停机
docker compose -f deploy/docker-compose.yml down
```

---

## 9. 无 Docker 的裸机方案（简）

1. 系统装 MySQL、Nginx、Python 3.12  
2. `python -m venv .venv && pip install -r requirements.txt gunicorn`  
3. `export FLASK_CONFIG=product` 并加载 env  
4. `gunicorn -c deploy/gunicorn.conf.py "wsgi:app"`  
5. Nginx 反代 `127.0.0.1:5000`，静态托管 `dist`  
6. systemd 托管 gunicorn + 定时备份  

---

## 10. 故障排查

| 现象 | 处理 |
|------|------|
| api 起不来 | `docker logs shop_api`，查 SECRET_KEY / 数据库连接 |
| 502 | api 未 healthy，或 nginx 上游名不是 `api` |
| 登录 500 scrypt | 跑 `reset_demo_passwords.py`（pbkdf2） |
| 前端调不通 API | 查 baseURL 与 CORS_ORIGINS |
| 跨域 | 设置 `CORS_ORIGINS` 或同域反代 |

---

## 11. 安全提醒

- 不要把 `deploy/.env.prod`、证书、备份提交 git  
- 生产禁止 `ALLOW_MOCK_PAY=1` 给真实顾客用  
- 定期改数据库密码与店长密码  
- 上传目录勿执行脚本（Nginx 仅静态）  

---

**部署完成后：** 用店长账号登录 `/admin/`，设置付款指引，用 mall 下单，后台 **标记已付款 → 发货** 验收。
