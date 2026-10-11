import csv
from datetime import date

from openpyxl import load_workbook

from flask_shop import db, models
from flask_shop.utils.tenant_query import tenant_context


def _create_live_tenant(app, slug="client-shop"):
    runner = app.test_cli_runner()
    result = runner.invoke(args=[
        "tenant", "create",
        "--slug", slug,
        "--name", "客户正式店铺",
        "--admin-name", "owner",
        "--admin-password", "StrongPass_2026",
        "--freight-fee", "8",
        "--free-shipping-amount", "99",
    ])
    assert result.exit_code == 0, result.output
    return runner


def test_formal_tenant_full_onboarding_and_live_dashboard(app, tmp_path):
    runner = _create_live_tenant(app)
    with app.app_context(), tenant_context(disabled=True):
        tenant = models.Tenant.query.filter_by(slug="client-shop").first()
        assert tenant is not None
        assert tenant.data_mode == "live"
        admin = models.User.query.filter_by(tenant_id=tenant.id, name="owner").first()
        assert admin.check_password("StrongPass_2026")
        assert admin.role.is_super == 1
        freight = models.FreightTemplate.query.filter_by(tenant_id=tenant.id, is_default=1).first()
        assert float(freight.fixed_fee) == 8

    templates = runner.invoke(args=["tenant", "templates", "--output-dir", str(tmp_path)])
    assert templates.exit_code == 0, templates.output
    assert (tmp_path / "products.csv").is_file()
    assert (tmp_path / "staff.csv").is_file()
    assert (tmp_path / "orders.csv").is_file()
    workbook = tmp_path / "onboarding.xlsx"
    assert workbook.is_file()
    book = load_workbook(workbook)
    book["products"].append(["示例商品", 99, 20, "默认分类", "验收商品", "no"])
    book["staff"].append(["service01", "客服一号", "客服", "StrongStaff_2026", "13800000000", ""])
    book["orders"].append([
        "HISTORY-001", "13800000001", "历史顾客", "示例商品", 1, 99,
        "completed", "2026-01-01 10:00:00", "2026-01-01 10:05:00", "历史订单地址",
    ])
    book.save(workbook)

    dry_run = runner.invoke(args=[
        "tenant", "import-data", "--slug", "client-shop",
        "--file", str(workbook), "--kind", "all", "--dry-run",
    ])
    assert dry_run.exit_code == 0, dry_run.output
    assert '"created_count": 3' in dry_run.output
    with app.app_context(), tenant_context(disabled=True):
        tenant = models.Tenant.query.filter_by(slug="client-shop").first()
        assert models.Product.query.filter_by(tenant_id=tenant.id).count() == 0

    imported = runner.invoke(args=[
        "tenant", "import-data", "--slug", "client-shop",
        "--file", str(workbook), "--kind", "all",
    ])
    assert imported.exit_code == 0, imported.output
    with app.app_context(), tenant_context(disabled=True):
        tenant = models.Tenant.query.filter_by(slug="client-shop").first()
        assert models.Product.query.filter_by(tenant_id=tenant.id, name="示例商品").count() == 1
        assert models.User.query.filter_by(tenant_id=tenant.id, name="service01").count() == 1
        order = models.Order.query.filter_by(tenant_id=tenant.id, order_no="HISTORY-001").first()
        assert order is not None
        assert order.attribution_source == "historical_import"

    client = app.test_client()
    login = client.post("/user/login/", json={
        "tenant_slug": "client-shop", "name": "owner", "pwd": "StrongPass_2026",
    }).get_json()
    assert login["status"] == 200
    dashboard = client.get("/dashboard/kpi/", headers={"token": login["data"]["token"]}).get_json()
    assert dashboard["status"] == 200
    assert dashboard["data"]["business"]["data_source"] == "live"


def test_import_error_report_and_live_demo_cleanup_guard(app, tmp_path):
    runner = _create_live_tenant(app, slug="guard-shop")
    bad_file = tmp_path / "products.csv"
    with bad_file.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["name", "price", "stock"])
        writer.writerow(["缺价格商品", "", "5"])
    error_file = tmp_path / "errors.csv"
    result = runner.invoke(args=[
        "tenant", "import-data", "--slug", "guard-shop",
        "--file", str(bad_file), "--kind", "products", "--error-file", str(error_file),
    ])
    assert result.exit_code == 1
    assert error_file.is_file()
    assert "商品价格格式不正确" in error_file.read_text(encoding="utf-8-sig")

    guarded = runner.invoke(args=[
        "tenant", "purge-demo-data", "--slug", "guard-shop",
        "--execute", "--confirm", "guard-shop",
    ])
    assert guarded.exit_code == 1
    assert "不是 demo 数据模式" in guarded.output or "只允许清理 demo" in guarded.output


def test_demo_cleanup_is_preview_first_and_marker_scoped(app):
    runner = app.test_cli_runner()
    with app.app_context(), tenant_context(disabled=True):
        tenant = models.Tenant(name="演示清理测试", slug="demo-clean", data_mode="demo", status=1)
        db.session.add(tenant)
        db.session.flush()
        product = models.Product(tenant_id=tenant.id, name="智能手环 S7", price=249, number=3)
        customer = models.Customer(tenant_id=tenant.id, phone="13800001001", nickname="演示顾客")
        db.session.add_all([product, customer])
        db.session.flush()
        order = models.Order(tenant_id=tenant.id, order_no="DEMO-BIZ-001", customer_id=customer.id, price=249)
        db.session.add(order)
        db.session.flush()
        db.session.add_all([
            models.OrderDetail(tenant_id=tenant.id, oid=order.id, pid=product.id, number=1, price=249, total_price=249),
            models.Payment(tenant_id=tenant.id, order_id=order.id, out_trade_no="DEMO-CLEAN-PAY", amount=249),
            models.AgentTrace(tenant_id=tenant.id, session_id="demo-clean-session", model="demo-data"),
            models.AdCampaignDaily(tenant_id=tenant.id, record_date=date.today(), platform="demo", campaign_name="演示", source="demo"),
        ])
        support = models.SupportConversation(tenant_id=tenant.id, session_id="demo-clean-session", customer_id=customer.id)
        db.session.add(support)
        db.session.flush()
        db.session.add(models.SupportMessage(tenant_id=tenant.id, conversation_id=support.id, sender_type="customer", content="演示"))
        db.session.commit()

    preview = runner.invoke(args=["tenant", "purge-demo-data", "--slug", "demo-clean"])
    assert preview.exit_code == 0, preview.output
    assert '"executed": false' in preview.output
    assert '"orders": 1' in preview.output
    with app.app_context(), tenant_context(disabled=True):
        assert models.Order.query.filter_by(order_no="DEMO-BIZ-001").count() == 1

    wrong_confirm = runner.invoke(args=[
        "tenant", "purge-demo-data", "--slug", "demo-clean", "--execute", "--confirm", "demo",
    ])
    assert wrong_confirm.exit_code == 1

    executed = runner.invoke(args=[
        "tenant", "purge-demo-data", "--slug", "demo-clean", "--execute", "--confirm", "demo-clean",
    ])
    assert executed.exit_code == 0, executed.output
    with app.app_context(), tenant_context(disabled=True):
        tenant = models.Tenant.query.filter_by(slug="demo-clean").first()
        assert models.Order.query.filter_by(tenant_id=tenant.id, order_no="DEMO-BIZ-001").count() == 0
        assert models.AgentTrace.query.filter_by(tenant_id=tenant.id, session_id="demo-clean-session").count() == 0
        assert models.Product.query.filter_by(tenant_id=tenant.id, name="智能手环 S7").first().number == 150
