import csv
from datetime import date
from decimal import Decimal

from openpyxl import load_workbook
import pytest

from flask_shop import db, models
from flask_shop.utils.tenant_query import tenant_context
from flask_shop.tenant_onboarding import OnboardingError, _integer, _money


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


def test_platform_create_uses_formal_onboarding_and_rejects_weak_input(app):
    app.config['PLATFORM_BOOTSTRAP_KEY'] = 'platform-test-secret-key'
    app.config['PLATFORM_API_ENABLED'] = True
    client = app.test_client()
    headers = {'X-Platform-Key': 'platform-test-secret-key'}
    payload = {'slug': 'platform-shop', 'name': '正式商家', 'admin_name': 'owner',
               'admin_password': 'StrongPass_2026', 'admin_phone': '13800000000',
               'admin_email': 'owner@example.test'}

    assert client.post('/api/p/tenants/', json=payload).get_json()['status'] == 401
    assert client.post('/api/p/tenants/', json=payload, headers={'X-Platform-Key': '错误密钥'}).get_json()['status'] == 401
    assert client.post('/api/p/tenants/', json={**payload, 'admin_password': 'password'}, headers=headers).get_json()['status'] == 400
    assert client.post('/api/p/tenants/', json={**payload, 'slug': 'demo-unsafe'}, headers=headers).get_json()['status'] == 400
    assert client.post('/api/p/tenants/', json={**payload, 'admin_name': ['invalid']}, headers=headers).get_json()['status'] == 400
    response = client.post('/api/p/tenants/', json=payload, headers=headers).get_json()
    assert response['status'] == 200
    assert client.post('/api/p/tenants/', json=payload, headers=headers).get_json()['status'] == 400

    with app.app_context(), tenant_context(disabled=True):
        tenant = models.Tenant.query.filter_by(slug='platform-shop').one()
        user = models.User.query.filter_by(tenant_id=tenant.id, name='owner').one()
        assert tenant.data_mode == 'live'
        assert user.is_admin == 1 and user.role.is_super == 1
        assert user.check_password(payload['admin_password'])
        assert user.phone == payload['admin_phone'] and user.email == payload['admin_email']
        assert models.FreightTemplate.query.filter_by(tenant_id=tenant.id, is_default=1).count() == 1
        assert user.role.menus

    login = client.post('/user/login/', json={
        'tenant_slug': 'platform-shop', 'name': 'owner', 'pwd': payload['admin_password'],
    }).get_json()
    assert login['status'] == 200


def test_disabled_platform_api_rejects_even_valid_key_without_changes(app):
    app.config['PLATFORM_BOOTSTRAP_KEY'] = 'platform-test-secret-key'
    app.config['PLATFORM_API_ENABLED'] = False
    client = app.test_client()
    headers = {'X-Platform-Key': 'platform-test-secret-key'}
    payload = {'slug': 'disabled-shop', 'name': '正式商家', 'admin_name': 'owner',
               'admin_password': 'StrongPass_2026'}
    for method, path, body in [
        ('post', '/api/p/tenants/', payload),
        ('get', '/api/p/tenants/', None),
        ('post', '/api/p/tenants/1/status/', {'status': 0}),
    ]:
        response = getattr(client, method)(path, json=body, headers=headers)
        assert response.status_code == 403
        assert response.get_json()['status'] == 403
    with app.app_context(), tenant_context(disabled=True):
        assert not models.Tenant.query.filter_by(slug='disabled-shop').first()
        assert models.Tenant.query.filter_by(slug='test-a').one().status == 1


@pytest.mark.parametrize('value', ['NaN', 'Infinity', '-Infinity', '10000000000', '0.004'])
def test_import_rejects_invalid_or_unrepresentable_prices(value):
    with pytest.raises(OnboardingError):
        _money(value, '价格', allow_zero=False)


@pytest.mark.parametrize('value', ['1.5', '-1', 'NaN', 'Infinity', '2147483648', '1e1000'])
def test_import_rejects_invalid_or_unrepresentable_integer(value):
    with pytest.raises(OnboardingError):
        _integer(value, '库存')


def test_import_numeric_rounding_matches_money_policy():
    assert _money('1.005', '价格') == Decimal('1.01')
    assert _integer('2.0', '库存') == 2


def test_staff_import_errors_never_echo_password(app, tmp_path):
    runner = _create_live_tenant(app, slug='redaction-shop')
    source = tmp_path / 'staff.csv'
    secret = 'StaffPassword_2026'
    with source.open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=['username', 'password', '密码', 'token'])
        writer.writeheader()
        writer.writerow({'username': '!', 'password': secret, '密码': secret, 'token': secret})
    result = runner.invoke(args=['tenant', 'import-data', '--slug', 'redaction-shop',
                                 '--file', str(source), '--kind', 'staff'])
    report = source.with_name('staff.errors.csv')
    assert result.exit_code == 1
    assert secret not in result.output
    assert secret not in report.read_text(encoding='utf-8-sig')
    assert '[已隐藏]' in report.read_text(encoding='utf-8-sig')


@pytest.mark.parametrize('dry_run', [True, False])
def test_import_rolls_back_failed_rows_and_redacts_exception(app, monkeypatch, dry_run):
    from flask_shop import tenant_onboarding

    _create_live_tenant(app, slug='rollback-shop')
    secret = 'secret-value-to-protect'

    def importer(tenant_id, row):
        product = models.Product.query.filter_by(tenant_id=tenant_id, name='恢复后的商品').first()
        if product:
            raise AssertionError('失败行遗留了商品')
        product = models.Product(tenant_id=tenant_id, name='恢复后的商品', price=1, number=1)
        db.session.add(product)
        db.session.flush()
        if row.get('fail'):
            raise ValueError(f'处理失败：{row["password"]}')
        return product

    monkeypatch.setitem(tenant_onboarding.IMPORTERS, 'products', importer)
    with app.app_context(), tenant_context(disabled=True):
        tenant = models.Tenant.query.filter_by(slug='rollback-shop').one()
        tenant_id = tenant.id
        db.session.commit()
        result = tenant_onboarding.import_initial_data('rollback-shop', {'products': [
            {'fail': True, 'password': secret}, {'fail': False},
        ]}, dry_run=dry_run)
        assert result['error_count'] == 1
        assert result['created_count'] == 1
        assert secret not in str(result)
        assert '[已隐藏]' in result['errors'][0]['reason']
        assert models.Product.query.filter_by(tenant_id=tenant_id, name='恢复后的商品').count() == (0 if dry_run else 1)


@pytest.mark.parametrize('dry_run', [True, False])
def test_import_continues_after_database_constraint_failure(app, monkeypatch, dry_run):
    from flask_shop import tenant_onboarding

    _create_live_tenant(app, slug='constraint-shop')

    def importer(tenant_id, row):
        if row.get('fail'):
            db.session.add(models.User(tenant_id=tenant_id, name='owner'))
            db.session.flush()
        product = models.Product(tenant_id=tenant_id, name='下一行商品', price=1, number=1)
        db.session.add(product)
        db.session.flush()
        return product

    monkeypatch.setitem(tenant_onboarding.IMPORTERS, 'products', importer)
    with app.app_context(), tenant_context(disabled=True):
        tenant_id = models.Tenant.query.filter_by(slug='constraint-shop').one().id
        db.session.commit()
        result = tenant_onboarding.import_initial_data('constraint-shop', {'products': [
            {'fail': True}, {'fail': False},
        ]}, dry_run=dry_run)
        assert result['error_count'] == 1 and result['created_count'] == 1
        assert models.Product.query.filter_by(tenant_id=tenant_id, name='下一行商品').count() == (0 if dry_run else 1)


def test_import_rejects_zero_quantity_and_overflow_without_creating_orders(app):
    from flask_shop.tenant_onboarding import import_initial_data

    _create_live_tenant(app, slug='numeric-shop')
    with app.app_context(), tenant_context(disabled=True):
        tenant = models.Tenant.query.filter_by(slug='numeric-shop').one()
        db.session.add(models.Product(tenant_id=tenant.id, name='商品', price=100, number=2))
        db.session.commit()
        base = {'customer_phone': '13800000000', 'product_name': '商品', 'unit_price': '9999999999.99'}
        result = import_initial_data('numeric-shop', {'orders': [
            {**base, 'order_no': 'ZERO', 'quantity': 0},
            {**base, 'order_no': 'OVERFLOW', 'quantity': 2},
        ]})
        assert result['error_count'] == 2
        assert models.Order.query.filter_by(tenant_id=tenant.id).count() == 0
        assert models.Customer.query.filter_by(tenant_id=tenant.id).count() == 0


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
