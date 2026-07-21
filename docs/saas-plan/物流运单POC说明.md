# 国际物流运单 POC

> 面向货代/国际物流场景的最小可用演示，复用现有多租户 + 登录 + RBAC。  
> **不是**完整 TMS，用于入职作品/业务沟通。

---

## 能力

| 功能 | 说明 |
|------|------|
| 运单 CRUD | 客户、起运/目的、件毛体、报价、提单号 |
| 状态机 | inquiry→quoted→booked→in_transit→arrived→delivered→closed；可取消 |
| 轨迹节点 | 手填地点+内容；改状态可自动写轨迹 |
| 附件 | 提单/箱单/发票等上传下载（≤15MB） |
| 内部后台 | `vue_shop` → **运单中心** |
| 客户查单 | `GET /api/c/shipment/track/?no=运单号` + `X-Tenant-Slug`（含附件列表） |

---

## 初始化

```bat
cd flask_shop
.venv\Scripts\activate
python scripts\migrate_shipment.py
python scripts\seed_shipments.py
python manager.py
```

刷新商户后台，侧栏 **运单中心**。

演示种子运单号（demo-a）：`SH1DEMO0001`

---

## 主要 API

| 方法 | 路径 | 权限 |
|------|------|------|
| GET/POST | `/shipments/` | shipment:read / write |
| GET/PUT | `/shipment/<id>/` | read / write |
| POST | `/shipment/<id>/transit/` | write，body: `{to_status, note?, location?}` |
| POST | `/shipment/<id>/events/` | write，body: `{content, location?}` |
| GET | `/shipment/<id>/documents/` | read 附件列表 |
| POST | `/shipment/<id>/documents/` | write，multipart `file` + `doc_type` + `title?` |
| DELETE | `/shipment/<sid>/documents/<did>/` | write 删除附件 |
| GET | `/shipments/summary/` | read |
| GET | `/api/c/shipment/track/?no=` | 公开只读（需租户头，含 documents） |

超级管理员默认全权限。

---

## 客户查轨迹（页面）

开发：

```text
http://127.0.0.1:5173/track?no=SH1DEMO0001&tenant=demo-a
http://127.0.0.1:5173/track?no=SH1DEMO0001&tenant=demo-a&lang=en
```

页内右上角可切换 **中文 / EN**，选择会写入 `localStorage.mall_locale`。  
商城顶栏全局也有语言切换。

## 客户查轨迹（API）

```http
GET /api/c/shipment/track/?no=SH1DEMO0001
X-Tenant-Slug: demo-a
```

---

## 与电商模块关系

- **并存**：零售订单仍在「订单中心」；物流运单在「运单中心」。
- 入职货代公司时可只演示运单模块，说明状态机与轨迹可扩展对接船司 API。

---

## 后续可增强（未做）

- 文件柜（提单/箱单/发票上传）
- 运价表与自动报价
- 客户公司主体与销售跟进 CRM
- 船司/轨迹 API 对接
- 中英双语界面
