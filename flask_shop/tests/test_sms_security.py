from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from threading import Barrier
from unittest.mock import patch

from flask_shop import db, models
from flask_shop.utils.sms import SMS_LOCKED_MESSAGE, send_login_code, verify_login_code
from flask_shop.utils.tenant_query import tenant_context


def add_code(app, tenant_id, phone, code, *, expires_at=None):
    with app.app_context(), tenant_context(disabled=True):
        db.session.add(models.SmsCode(
            tenant_id=tenant_id, phone=phone, code=code, scene='login', used=0,
            expires_at=expires_at or datetime.now() + timedelta(minutes=10),
        ))
        db.session.commit()


def test_sms_guesses_are_limited_per_tenant_and_phone(api, app):
    tenant_id = api['seed']['id_a']
    phone = '13800138000'
    add_code(app, tenant_id, phone, '123456')
    client = api['client']
    for index in range(5):
        result = client.post('/api/c/auth/sms/login/', headers={
            'X-Tenant-Slug': 'test-a', 'X-Forwarded-For': f'198.51.100.{index + 1}',
        }, json={'phone': phone, 'code': '000000'})
        assert result.get_json()['status'] == 400

    locked = client.post('/api/c/auth/sms/login/', headers={'X-Tenant-Slug': 'test-a'},
                         json={'phone': phone, 'code': '123456'})
    assert locked.status_code == 429
    assert locked.get_json()['msg'] == SMS_LOCKED_MESSAGE

    other_tenant = api['seed']['id_b']
    add_code(app, other_tenant, phone, '123456')
    other = client.post('/api/c/auth/sms/login/', headers={'X-Tenant-Slug': 'test-b'},
                        json={'phone': phone, 'code': '123456'})
    assert other.get_json()['status'] == 200
    with app.app_context(), tenant_context(disabled=True):
        throttle = models.LoginThrottle.query.filter_by(scope='sms_account').filter(
            models.LoginThrottle.locked_until.isnot(None)
        ).one()
        throttle.locked_until = datetime.now() - timedelta(seconds=1)
        db.session.commit()

    unlocked = client.post('/api/c/auth/sms/login/', headers={'X-Tenant-Slug': 'test-a'},
                           json={'phone': phone, 'code': '123456'})
    assert unlocked.get_json()['status'] == 200
    replay = client.post('/api/c/auth/sms/login/', headers={'X-Tenant-Slug': 'test-a'},
                         json={'phone': phone, 'code': '123456'})
    assert replay.get_json()['status'] == 400


def test_only_latest_unexpired_sms_code_can_be_consumed(api, app):
    tenant_id = api['seed']['id_a']
    phone = '13800138001'
    add_code(app, tenant_id, phone, '111111')
    add_code(app, tenant_id, phone, '222222')
    with app.app_context(), tenant_context(tenant_id=tenant_id):
        assert verify_login_code(tenant_id, phone, '111111')[0] is False
    expired_phone = '13800138004'
    add_code(app, tenant_id, expired_phone, '333333', expires_at=datetime.now() - timedelta(seconds=1))
    with app.app_context(), tenant_context(tenant_id=tenant_id):
        assert verify_login_code(tenant_id, expired_phone, '333333')[0] is False
        assert verify_login_code(tenant_id, phone, '222222')[0] is True
        assert verify_login_code(tenant_id, phone, '111111')[0] is False


def test_one_sms_code_cannot_be_consumed_by_concurrent_requests(api, app):
    tenant_id = api['seed']['id_a']
    phone = '13800138002'
    add_code(app, tenant_id, phone, '123456')
    barrier = Barrier(2)

    def attempt():
        with app.app_context(), tenant_context(tenant_id=tenant_id):
            barrier.wait(timeout=10)
            return verify_login_code(tenant_id, phone, '123456')[0]

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [future.result(timeout=20) for future in [pool.submit(attempt), pool.submit(attempt)]]
    assert sorted(results) == [False, True]


def test_correct_fifth_sms_attempt_succeeds_and_clears_failures(api, app):
    tenant_id = api['seed']['id_a']
    phone = '13800138006'
    add_code(app, tenant_id, phone, '123456')
    with app.app_context(), tenant_context(tenant_id=tenant_id):
        for _ in range(4):
            assert verify_login_code(tenant_id, phone, '000000')[0] is False
        assert verify_login_code(tenant_id, phone, '123456') == (True, None)
        throttle = models.LoginThrottle.query.filter_by(scope='sms_account').one()
        assert throttle.failed_count == 0
        assert throttle.locked_until is None


def test_concurrent_sms_guesses_do_not_bypass_attempt_limit(api, app):
    tenant_id = api['seed']['id_a']
    phone = '13800138005'
    add_code(app, tenant_id, phone, '123456')
    barrier = Barrier(6)

    def attempt():
        with app.app_context(), tenant_context(tenant_id=tenant_id):
            barrier.wait(timeout=10)
            return verify_login_code(tenant_id, phone, '000000')

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = [future.result(timeout=30) for future in [pool.submit(attempt) for _ in range(6)]]
    assert all(not success for success, _ in results)
    assert sum(message == SMS_LOCKED_MESSAGE for _, message in results) == 1
    with app.app_context(), tenant_context(tenant_id=tenant_id):
        assert verify_login_code(tenant_id, phone, '123456') == (False, SMS_LOCKED_MESSAGE)


def test_dev_sms_generation_uses_secure_random_source(api):
    with patch('flask_shop.utils.sms.secrets.randbelow', return_value=7) as random_code:
        response = api['client'].post('/api/c/auth/sms/send/', headers={'X-Tenant-Slug': 'test-a'},
                                      json={'phone': '13800138003'}).get_json()
    assert response['data']['dev_code'] == '000007'
    random_code.assert_called_once_with(1000000)


def test_sms_send_limit_uses_real_ip_and_failed_ip_limit_does_not_consume_phone(api, app):
    app.config.update(SMS_DEV_MODE=False, SMS_SEND_IP_LIMIT=2, SMS_SEND_IP_WINDOW_SECONDS=60)
    client = api['client']
    with patch('flask_shop.utils.sms._send_via_provider', return_value=(True, None)) as provider:
        for index in range(3):
            result = client.post('/api/c/auth/sms/send/', headers={
                'X-Tenant-Slug': 'test-a', 'X-Forwarded-For': f'198.51.100.{index + 1}',
            }, environ_base={'REMOTE_ADDR': '203.0.113.10'}, json={'phone': f'138001380{10 + index}'})
            assert result.status_code == (200 if index < 2 else 429)
        other_ip = client.post('/api/c/auth/sms/send/', headers={'X-Tenant-Slug': 'test-a'},
                               environ_base={'REMOTE_ADDR': '203.0.113.11'}, json={'phone': '13800138012'})
        assert other_ip.get_json()['status'] == 200
    assert provider.call_count == 3


def test_concurrent_sms_sends_for_same_phone_call_provider_once(api, app):
    tenant_id = api['seed']['id_a']
    phone = '13800138013'
    app.config.update(SMS_DEV_MODE=False)
    barrier = Barrier(2)

    def send():
        with app.test_request_context('/', environ_base={'REMOTE_ADDR': '203.0.113.15'}), tenant_context(tenant_id=tenant_id):
            barrier.wait(timeout=10)
            return send_login_code(tenant_id, phone)

    with patch('flask_shop.utils.sms._send_via_provider', return_value=(True, None)) as provider:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = [future.result(timeout=20) for future in [pool.submit(send), pool.submit(send)]]
    assert sum(payload is not None for payload, _ in results) == 1
    assert provider.call_count == 1


def test_failed_sms_provider_still_consumes_send_cooldown(api, app):
    app.config.update(SMS_DEV_MODE=False)
    client = api['client']
    with patch('flask_shop.utils.sms._send_via_provider', return_value=(False, '失败')) as provider:
        first = client.post('/api/c/auth/sms/send/', headers={'X-Tenant-Slug': 'test-a'},
                            json={'phone': '13800138014'})
        second = client.post('/api/c/auth/sms/send/', headers={'X-Tenant-Slug': 'test-b'},
                             json={'phone': '13800138014'})
    assert first.get_json()['status'] == 400
    assert second.status_code == 429
    assert provider.call_count == 1


def test_concurrent_sms_sends_share_persistent_ip_limit(api, app):
    tenant_id = api['seed']['id_a']
    app.config.update(SMS_DEV_MODE=False, SMS_SEND_IP_LIMIT=1)
    barrier = Barrier(2)

    def send(phone):
        with app.test_request_context('/', environ_base={'REMOTE_ADDR': '203.0.113.20'}), tenant_context(tenant_id=tenant_id):
            barrier.wait(timeout=10)
            return phone, send_login_code(tenant_id, phone)

    with patch('flask_shop.utils.sms._send_via_provider', return_value=(True, None)) as provider:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = [future.result(timeout=20) for future in [
                pool.submit(send, '13800138015'), pool.submit(send, '13800138016'),
            ]]
        assert sum(payload is not None for _, (payload, _) in results) == 1
        denied_phone = next(phone for phone, (payload, _) in results if payload is None)
        with app.test_request_context('/', environ_base={'REMOTE_ADDR': '203.0.113.21'}), tenant_context(tenant_id=tenant_id):
            assert send_login_code(tenant_id, denied_phone)[0] is not None
    assert provider.call_count == 2
