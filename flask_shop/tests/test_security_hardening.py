from datetime import datetime, timedelta

from flask_shop import db, models
from flask_shop.utils.tenant_query import tenant_context


def test_login_failure_lockout_is_persistent_and_success_clears_account(api, app):
    client = api['client']
    seed = api['seed']
    headers = {'X-Forwarded-For': '198.51.100.44'}
    for _ in range(4):
        response = client.post(
            '/user/login/',
            json={'tenant_slug': 'test-a', 'name': 'admin_a', 'pwd': 'wrong'},
            headers=headers,
        )
        assert response.status_code == 200
        assert response.get_json()['status'] == 400

    locked = client.post(
        '/user/login/',
        json={'tenant_slug': 'test-a', 'name': 'admin_a', 'pwd': 'wrong'},
        headers=headers,
    )
    assert locked.status_code == 429
    assert locked.get_json()['status'] == 429

    with app.app_context(), tenant_context(disabled=True):
        row = models.LoginThrottle.query.filter_by(scope='account').first()
        assert row is not None
        assert row.failed_count >= 5
        assert row.locked_until > datetime.now()

    # 账户锁定不能靠正确密码绕过。
    still_locked = client.post(
        '/user/login/',
        json={'tenant_slug': 'test-a', 'name': 'admin_a', 'pwd': '123456'},
        headers=headers,
    )
    assert still_locked.status_code == 429

    omitted_tenant = client.post(
        '/user/login/',
        json={'name': 'admin_a', 'pwd': '123456'},
        headers={'X-Forwarded-For': '198.51.100.45'},
    )
    assert omitted_tenant.status_code == 429

    with app.app_context(), tenant_context(disabled=True):
        row = models.LoginThrottle.query.filter_by(scope='account').first()
        row.locked_until = datetime.now() - timedelta(seconds=1)
        db.session.commit()

    success = client.post(
        '/user/login/',
        json={'tenant_slug': 'test-a', 'name': 'admin_a', 'pwd': '123456'},
        headers={'X-Forwarded-For': '198.51.100.45'},
    )
    assert success.status_code == 200
    assert success.get_json()['status'] == 200
    with app.app_context(), tenant_context(disabled=True):
        row = models.LoginThrottle.query.filter_by(scope='account').first()
        assert row.failed_count == 0
        assert row.locked_until is None


def test_security_headers_and_health_do_not_expose_environment(api):
    response = api['client'].get('/health/')
    assert response.status_code == 200
    body = response.get_json()
    assert body == {'status': 200, 'msg': 'ok', 'app': 'ecommerce-shop'}
    assert response.headers['X-Content-Type-Options'] == 'nosniff'
    assert response.headers['X-Frame-Options'] == 'DENY'
    assert response.headers['Referrer-Policy'] == 'strict-origin-when-cross-origin'
    assert 'env' not in body


def test_security_tips_are_returned_for_demo_login(api):
    response = api['client'].post(
        '/user/login/',
        json={'tenant_slug': 'test-a', 'name': 'admin_a', 'pwd': '123456'},
        headers={'X-Forwarded-For': '198.51.100.77'},
    )
    assert response.get_json()['status'] == 200
    tips = response.get_json()['data']['security_tips']
    assert any('默认密码' in tip for tip in tips)
    assert any('开发验证码' in tip for tip in tips)
