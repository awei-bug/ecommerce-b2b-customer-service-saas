# Flask Shop 后端

## 环境要求

- Python 3.10+（已在 3.12 + venv 验证）
- MySQL 5.7+ / 8.x

## 1. 创建并使用虚拟环境（推荐）

在 `flask_shop` 目录下：

### Windows（CMD）

```bat
python -m venv .venv
.venv\Scripts\activate.bat
python -m pip install -U pip
pip install -r requirements.txt
```

### Windows（PowerShell）

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -r requirements.txt
```

### Git Bash

```bash
python -m venv .venv
source .venv/Scripts/activate
python -m pip install -U pip
pip install -r requirements.txt
```

激活成功后，命令行前缀一般会出现 `(.venv)`。

**不要**在未激活 venv 时用全局 Anaconda 再 `pip install`，否则依赖会装到全局环境。

### 不用激活、直接调用 venv 里的 Python

```bat
.venv\Scripts\python.exe manager.py
.venv\Scripts\python.exe scripts\seed_tenants.py
```

## 2. 配置环境变量

```bat
copy .env.example .env
```

编辑 `.env`：数据库账号、`SECRET_KEY` 等。  
**不要提交 `.env`。**

## 3. 启动 API

```bat
python manager.py
```

默认：`http://127.0.0.1:5000`

## 4. 常用脚本（均在已激活的 venv 中执行）

```bat
python scripts\seed_tenants.py
python scripts\migrate_l0_ops.py
python scripts\migrate_rbac_actions.py
python scripts\migrate_l1_features.py
python scripts\migrate_commercial_manual_pay.py
python scripts\seed_rbac_roles.py --with-users
python scripts\seed_freight.py
python scripts\reset_demo_passwords.py
python scripts\verify_rbac.py
python scripts\verify_l1_features.py
python scripts\verify_mark_paid.py
```

### 商用带货（无官方支付）要点

- 开发：`.env` 可 `ALLOW_MOCK_PAY=1`  
- 生产：必须 `ALLOW_MOCK_PAY=0`  
- 店长在订单中心对「待支付」点 **标记已付款**（线下收款后）  
- 在 **店铺设置** 填写 **付款指引**，顾客下单后可见  

## 5. VS Code / Cursor 解释器

请选择：

```text
F:\Python_code\Flask项目\flask_shop\.venv\Scripts\python.exe
```

若 `requirements.txt` 仍提示「未在所选环境中安装包」，多半是 IDE 还在用 Anaconda 全局解释器，切换到上面的 `.venv` 即可。

## 6. 与前端

| 项目 | 说明 |
|------|------|
| `vue_shop` | 商户后台，`npm install` + `npm run serve` |
| `mall` | C 端商城，`npm install` + `npm run dev` |

后端 API 地址默认 `http://localhost:5000`。
