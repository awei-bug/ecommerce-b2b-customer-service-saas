"""??????????? / ?? / ????? / ?????? GET?"""
import pytest

from config import ProductionConfig
from flask_shop.utils.money import money_add, money_float, money_mul, to_money


def test_money_helpers_round_half_up():
    assert str(to_money('1.005')) == '1.01'
    assert money_float('10.1') == 10.1
    assert money_mul('3.33', 3) == 9.99
    assert money_add(0.1, 0.2) == 0.3


def test_production_validate_rejects_weak_defaults():
    class _P(ProductionConfig):
        SECRET_KEY = 'short'
        ALLOW_MOCK_PAY = True
        SMS_DEV_MODE = True
        PLATFORM_BOOTSTRAP_KEY = 'dev-platform-key-change-me'
        CORS_ORIGINS = ['*']
        PUBLIC_BASE_URL = 'http://127.0.0.1:5000'
        PAY_DEFAULT_CHANNEL = 'mock'

    with pytest.raises(RuntimeError) as ei:
        _P.validate()
    msg = str(ei.value)
    assert 'SECRET_KEY' in msg or '??' in msg or 'ALLOW_MOCK_PAY' in msg


def test_production_validate_rejects_console_sms_and_weak_database_password():
    class _P(ProductionConfig):
        SECRET_KEY = 'x' * 48
        ALLOW_MOCK_PAY = False
        SMS_DEV_MODE = False
        SMS_PROVIDER = 'console'
        MYSQL_PASSWORD = 'short'
        PLATFORM_BOOTSTRAP_KEY = 'p' * 32
        CORS_ORIGINS = ['https://shop.example.com']
        PUBLIC_BASE_URL = 'https://shop.example.com'
        _db_url = ''

    with pytest.raises(RuntimeError) as ei:
        _P.validate()
    message = str(ei.value)
    assert '数据库密码' in message
    assert 'SMS_PROVIDER' in message


def test_create_app_develop_ok():
    from flask_shop import create_app
    app = create_app('develop')
    assert app.config.get('DEBUG') is True


def test_reset_password_get_rejected(api):
    client = api['client']
    seed = api['seed']
    # ???? A ??? token??? id ? seed ?????? 1
    uid = getattr(seed.get('ta'), 'id', None)  # placeholder
    # seed ?? token_a????????????? token ?????? reset ?? id
    headers = {'token': seed['token_a']}
    # ??????????????? 200 ??????? GET ??
    # ?????? user id?????????????????? me ??? 1
    rv = client.get('/user/user/1/reset_pwd/', headers=headers)
    body = rv.get_json(silent=True) or {}
    # GET ?????
    assert rv.status_code == 405 or (rv.status_code == 200 and body.get('status') == 405)
