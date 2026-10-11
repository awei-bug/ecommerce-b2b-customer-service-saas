# -*- coding: utf-8 -*-
"""Idempotently create a complete, clearly labelled business demo for tenant demo."""
from __future__ import annotations

import os
import sys
from datetime import date, datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from flask_shop import create_app, db, models  # noqa: E402
from flask_shop.utils.tenant_query import tenant_context  # noqa: E402


def upsert(model, defaults=None, **keys):
    row = model.query.filter_by(**keys).first()
    if not row:
        row = model(**keys)
        db.session.add(row)
    for name, value in (defaults or {}).items():
        setattr(row, name, value)
    db.session.flush()
    return row


def main():
    app = create_app(os.getenv("FLASK_CONFIG", "develop"))
    now = datetime.now().replace(second=0, microsecond=0)
    with app.app_context(), tenant_context(disabled=True):
        tenant = models.Tenant.query.filter_by(slug="demo").first()
        if not tenant:
            raise RuntimeError("缺少 demo 租户，请先运行 scripts/seeds/seed_shop.py")
        admin = models.User.query.filter_by(tenant_id=tenant.id, name="admin").first()
        products = models.Product.query.filter_by(tenant_id=tenant.id).order_by(models.Product.id.asc()).all()
        if not admin or not products:
            raise RuntimeError("demo 租户缺少管理员或商品，请先运行 seed_shop.py")

        customers = []
        for index, (phone, nickname) in enumerate([
            ("13800001001", "林女士"),
            ("13800001002", "陈先生"),
            ("13800001003", "周女士"),
            ("13800001004", "王先生"),
        ]):
            customers.append(upsert(
                models.Customer,
                {"nickname": nickname, "status": 1, "create_time": now - timedelta(days=12 - index)},
                tenant_id=tenant.id,
                phone=phone,
            ))

        order_specs = [
            ("DEMO-BIZ-001", customers[0], 599, "completed", 6, "demo-ai-001"),
            ("DEMO-BIZ-002", customers[1], 299, "shipped", 4, "demo-ai-002"),
            ("DEMO-BIZ-003", customers[2], 189, "paid", 2, "demo-human-001"),
            ("DEMO-BIZ-004", customers[3], 249, "pending_pay", 1, "demo-ai-003"),
            ("DEMO-BIZ-005", customers[0], 129, "refunding", 0, "demo-human-002"),
            ("DEMO-BIZ-006", customers[1], 68, "pending_pay", 0, None),
        ]
        orders = []
        for index, (order_no, customer, amount, status, days_ago, session_id) in enumerate(order_specs):
            created = now - timedelta(days=days_ago, hours=index)
            paid_at = created + timedelta(minutes=8) if status in {"paid", "shipped", "completed", "refunding"} else None
            order = upsert(models.Order, {
                "customer_id": customer.id,
                "price": amount,
                "goods_amount": amount,
                "freight_amount": 0,
                "number": 1,
                "status": status,
                "pay_status": 1 if paid_at else 0,
                "is_send": 1 if status in {"shipped", "completed"} else 0,
                "address": f"演示地址 {index + 1} 号",
                "paid_at": paid_at,
                "shipped_at": paid_at + timedelta(hours=4) if status in {"shipped", "completed"} else None,
                "buyer_paid_claimed": 1 if order_no == "DEMO-BIZ-004" else 0,
                "buyer_paid_at": created + timedelta(minutes=5) if order_no == "DEMO-BIZ-004" else None,
                "buyer_paid_note": "演示转账 1004" if order_no == "DEMO-BIZ-004" else None,
                "consultation_session_id": session_id,
                "attribution_source": "demo",
                "attribution_medium": "business_scenario",
                "create_time": created,
            }, tenant_id=tenant.id, order_no=order_no)
            orders.append(order)
            if not models.OrderDetail.query.filter_by(tenant_id=tenant.id, oid=order.id).first():
                product = products[index % len(products)]
                db.session.add(models.OrderDetail(
                    tenant_id=tenant.id,
                    oid=order.id,
                    pid=product.id,
                    number=1,
                    price=amount,
                    total_price=amount,
                ))
            if paid_at:
                upsert(models.Payment, {
                    "channel": "demo_manual",
                    "amount": amount,
                    "status": "success",
                    "transaction_id": f"DEMO-TX-{index + 1:03d}",
                    "paid_at": paid_at,
                    "create_time": created,
                }, tenant_id=tenant.id, order_id=order.id, out_trade_no=f"DEMO-PAY-{index + 1:03d}")

        session_specs = [
            ("demo-ai-001", customers[0], 0, 0, "catalog", "completed"),
            ("demo-ai-002", customers[1], 0, 0, "order", "completed"),
            ("demo-ai-003", customers[3], 0, 0, "promo", "pending_pay"),
            ("demo-human-001", customers[2], 1, 0, "refund", "paid"),
            ("demo-human-002", customers[0], 1, 0, "refund", "refunding"),
            ("demo-risk-001", customers[3], 1, 1, "risk", None),
        ]
        for index, (session_id, customer, need_human, blocked, intent, _order_status) in enumerate(session_specs):
            created = now - timedelta(days=index + 1)
            upsert(models.AgentTrace, {
                "channel": "mall_chat",
                "user_text": "演示顾客咨询",
                "reply": "演示 AI 回复",
                "intent": intent,
                "agents_ran": "intent,cs",
                "model": "demo-data",
                "need_human": need_human,
                "blocked": blocked,
                "customer_id": customer.id,
                "latency_ms": 420,
                "create_time": created,
            }, tenant_id=tenant.id, session_id=session_id)

        support_specs = [
            ("demo-human-001", customers[2], "resolved", "high", 5, 4),
            ("demo-human-002", customers[0], "active", "urgent", None, 3),
            ("demo-risk-001", customers[3], "waiting", "urgent", None, None),
        ]
        for index, (session_id, customer, status, priority, satisfaction, response_minutes) in enumerate(support_specs):
            created = now - timedelta(hours=index + 2)
            row = upsert(models.SupportConversation, {
                "customer_id": customer.id,
                "assignee_id": admin.id if status != "waiting" else None,
                "status": status,
                "priority": priority,
                "intent": "refund" if index < 2 else "risk",
                "subject": "演示退款咨询" if index < 2 else "演示高风险咨询",
                "last_message": "这是用于交付验收的演示会话",
                "message_count": 4 if status != "waiting" else 2,
                "need_human": 1,
                "first_response_at": created + timedelta(minutes=response_minutes) if response_minutes else None,
                "resolved_at": created + timedelta(minutes=18) if status == "resolved" else None,
                "satisfaction": satisfaction,
                "satisfaction_note": "处理及时" if satisfaction else None,
                "create_time": created,
            }, tenant_id=tenant.id, session_id=session_id)
            if row.messages.count() == 0:
                db.session.add_all([
                    models.SupportMessage(tenant_id=tenant.id, conversation_id=row.id, sender_type="customer", sender_id=customer.id, content="请帮我处理这个订单问题", create_time=created),
                    models.SupportMessage(tenant_id=tenant.id, conversation_id=row.id, sender_type="ai", content="已为你转接人工客服", create_time=created + timedelta(seconds=10)),
                ])
                if status != "waiting":
                    db.session.add(models.SupportMessage(tenant_id=tenant.id, conversation_id=row.id, sender_type="staff", sender_id=admin.id, content="您好，我正在为您核对处理", create_time=row.first_response_at))

        for days_ago, spend, revenue, order_count in [(0, 120, 420, 3), (1, 90, 180, 2), (2, 80, 96, 1)]:
            upsert(models.AdCampaignDaily, {
                "spend": spend,
                "revenue": revenue,
                "orders": order_count,
                "clicks": 90 - days_ago * 10,
                "impressions": 2800 - days_ago * 300,
                "source": "demo",
            }, tenant_id=tenant.id, record_date=date.today() - timedelta(days=days_ago), platform="demo", campaign_name="演示新品推广")

        knowledge_specs = [
            ("演示付款方式", "payment", "支持哪些付款方式", "顾客下单后扫描店铺收款码转账，并备注订单号；店长核对到账后人工确认收款。", ["付款", "支付", "收款码", "转账"], 90),
            ("演示发货时效", "shipping", "付款后多久发货", "现货订单通常在店长确认收款后 48 小时内发出，节假日顺延。", ["发货", "配送", "多久发货"], 80),
            ("演示退货规则", "refund", "是否支持退货退款", "未拆封且不影响二次销售的商品，可在签收后 7 天内联系人工客服核对退货；定制及特殊商品除外。", ["退货", "退款", "七天无理由", "售后"], 85),
            ("演示常见商品问题", "product", "商品缺货后怎么办", "页面显示缺货时暂时无法下单，可联系人工客服登记到货提醒。", ["缺货", "库存", "到货提醒"], 40),
        ]
        for title, category, question, content, keywords, priority in knowledge_specs:
            row = upsert(models.StoreKnowledge, {
                "category": category,
                "question": question,
                "content": content,
                "status": "published",
                "priority": priority,
                "source_type": "demo",
                "source_label": "演示知识库",
            }, tenant_id=tenant.id, title=title)
            row.set_keywords(keywords)

        products[-1].number = 3
        db.session.commit()
        print("business demo ready: 4 customers, 6 orders, 6 AI sessions, 3 support cases, 4 knowledge entries")
        print("all generated records are labelled demo and may be refreshed idempotently")


if __name__ == "__main__":
    main()
