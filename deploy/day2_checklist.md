# Day2 检查清单：备份 + HTTPS + 进程守护

> 对应《2周私有化内测冲刺清单》Day2–3。  
> Day1 配置与 Compose 见 [`day1_checklist.md`](./day1_checklist.md)。

**目标 RPO/RTO（内测默认）：**

| 指标 | 目标 |
|------|------|
| RPO | ≤ 24 小时（每日备份） |
| RTO | ≤ 4 小时（有备份文件 + 文档可恢复） |

---

## A. 数据库与上传目录备份

### A1. Linux / Git Bash / Docker

```bash
# 在仓库根目录
# 若用 Compose，容器名默认 shop_mysql，端口映射常见 3307
export MYSQL_HOST=127.0.0.1
export MYSQL_PORT=3307
export MYSQL_USERNAME=shop          # 或 root
export MYSQL_PASSWORD='你的密码'
export MYSQL_DB=flask_shop_saas
export BACKUP_DIR=deploy/backups
export BACKUP_KEEP_DAYS=7

bash deploy/backup_mysql.sh
# 同时打上传目录包（可选）
bash deploy/backup_all.sh
```

- [ ] `deploy/backups/` 下出现 `flask_shop_*.sql.gz`
- [ ] （可选）出现 `uploads_*.tar.gz` 或 `uploads_*.zip`

### A2. Windows 本机 MySQL（无 Docker）

```bat
deploy\win\backup_mysql.bat
```

会读取 `flask_shop\.env` 里的 `MYSQL_*`（若存在），备份到 `deploy\backups\`。

- [ ] 生成 `.sql` 或 `.sql.gz`
- [ ] 文件大小 > 0

### A3. 恢复演练（必做一次）

**不要在生产库上直接恢复！** 使用临时库：

```bash
# 示例：解压并导入到临时库
gunzip -c deploy/backups/flask_shop_flask_shop_saas_YYYYMMDD_HHMMSS.sql.gz \
  | mysql -h127.0.0.1 -P3306 -uroot -p -e "CREATE DATABASE IF NOT EXISTS flask_shop_restore_test DEFAULT CHARSET utf8mb4;"

gunzip -c deploy/backups/flask_shop_flask_shop_saas_YYYYMMDD_HHMMSS.sql.gz \
  | mysql -h127.0.0.1 -P3306 -uroot -p flask_shop_restore_test

mysql -h127.0.0.1 -uroot -p -e "USE flask_shop_restore_test; SHOW TABLES; SELECT id,slug FROM t_tenants LIMIT 5;"
```

Windows 可先用解压工具得到 `.sql`，再用：

```bat
mysql -uroot -p123456 -e "CREATE DATABASE IF NOT EXISTS flask_shop_restore_test DEFAULT CHARSET utf8mb4;"
mysql -uroot -p123456 flask_shop_restore_test < deploy\backups\xxx.sql
```

- [ ] 临时库能看到 `t_tenants` / `t_order` 等表  
- [ ] 能查出 demo 或业务租户  
- [ ] 演练后删除临时库：`DROP DATABASE flask_shop_restore_test;`

### A4. 定时任务

**Linux cron（每天 3:15）：**

```cron
15 3 * * * cd /path/to/repo && . deploy/.env.prod && bash deploy/backup_all.sh >> /var/log/shop_backup.log 2>&1
```

**Windows 任务计划程序：**

- 程序：`F:\Python_code\Flask项目\deploy\win\backup_mysql.bat`
- 触发器：每天一次

- [ ] 定时任务已创建（或写明「人工每日执行」过渡）

---

## B. HTTPS（有域名时）

### B1. 证书

- [ ] 域名 A 记录指向服务器  
- [ ] 申请证书（Let’s Encrypt / 云厂商）  
- [ ] 将 `fullchain.pem`、`privkey.pem` 放到 `deploy/certs/`

### B2. Nginx

- [ ] 参考 `nginx/conf.d/default.ssl.conf.example`  
- [ ] 已包含 `/dashboard`、`/payments` 与业务 API 前缀  
- [ ] 80 → 443 跳转  
- [ ] 重载 Nginx / 重启 compose nginx 容器

### B3. 无域名临时方案（仅内测）

- [ ] 继续用 `http://IP:18080`  
- [ ] 或用 cpolar/ngrok 出 HTTPS 隧道（仅演示，不替代正式证书）

**Day2 HTTPS 最低标准：** 要么正式证书，要么书面记录「本周仅 HTTP 内测，风险已知」。

---

## C. 进程守护

### C1. Docker Compose（已具备）

- [ ] `restart: unless-stopped` 已在 compose 中  
- [ ] `docker compose ps` 异常退出后会拉起  

### C2. 无 Docker：systemd（Linux API 示例）

见 `deploy/systemd/flask-shop-api.service.example`：

```bash
sudo cp deploy/systemd/flask-shop-api.service.example /etc/systemd/system/flask-shop-api.service
# 编辑 User/WorkingDirectory/EnvironmentFile
sudo systemctl daemon-reload
sudo systemctl enable --now flask-shop-api
sudo systemctl status flask-shop-api
```

### C3. Windows

- [ ] 开发：手动 `manager.py` / 任务计划「登录时运行」  
- [ ] 或使用 NSSM 把 `start_api_prod.bat` 注册为服务（可选）

---

## D. 探活与日志

```bash
bash deploy/healthcheck.sh
API_URL=http://127.0.0.1:5000 PUBLIC_URL=http://127.0.0.1:18080 bash deploy/healthcheck.sh
```

- [ ] `/health/` 200  
- [ ] （Compose）`/healthz` 200  
- [ ] 知道日志在哪：`docker compose logs -f api` 或 waitress/gunicorn 控制台  

---

## E. Day2 出口（今晚）

| # | 标准 | ☐ |
|---|------|---|
| 1 | 至少 1 份可用的 MySQL 备份文件 | ☐ |
| 2 | 完成 1 次恢复到**临时库**演练 | ☐ |
| 3 | 上传目录有备份或说明「暂无用户图、下周补」 | ☐ |
| 4 | 进程守护策略写明（Compose / systemd / 人工） | ☐ |
| 5 | HTTPS 已上或书面接受本周 HTTP | ☐ |
| 6 | RPO=24h / RTO=4h 已记入本文顶部 | ☐ |

---

## F. 相关文件

| 文件 | 作用 |
|------|------|
| `backup_mysql.sh` | Linux/Docker 逻辑备份 |
| `backup_all.sh` | 库 + 上传目录 |
| `win/backup_mysql.bat` | Windows 本机备份 |
| `win/restore_mysql_test.bat` | Windows 恢复到测试库（交互） |
| `nginx/conf.d/default.ssl.conf.example` | HTTPS 样例 |
| `systemd/flask-shop-api.service.example` | systemd 样例 |

---

## G. 今天不要做

- 加业务功能  
- 真微信支付进件  
- 公开注册  

**明天 Day3：** 若备份未自动定时，补 cron；开始 Day4 收款流程固化。
