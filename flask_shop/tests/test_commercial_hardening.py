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
        SQLALCHEMY_DATABASE_URI = 'mysql+pymysql://shop:short@localhost/shop'
        PLATFORM_BOOTSTRAP_KEY = 'p' * 32
        CORS_ORIGINS = ['https://shop.example.com']
        PUBLIC_BASE_URL = 'https://shop.example.com'
        _db_url = ''

    with pytest.raises(RuntimeError) as ei:
        _P.validate()
    message = str(ei.value)
    assert '数据库密码' in message
    assert 'SMS_PROVIDER' in message


def test_production_rejects_unimplemented_or_insecure_sms_provider(monkeypatch):
    monkeypatch.setenv('PRIVATE_DEPLOY', '0')

    class Config(ProductionConfig):
        SECRET_KEY = 'x' * 48
        ALLOW_MOCK_PAY = False
        SMS_DEV_MODE = False
        SMS_PROVIDER = 'aliyun'
        SMS_HTTP_URL = 'https://sms.example.test/send'
        MYSQL_PASSWORD = 'strong-database-password'
        SQLALCHEMY_DATABASE_URI = 'mysql+pymysql://shop:strong-database-password@localhost/shop'
        PLATFORM_BOOTSTRAP_KEY = 'p' * 32
        CORS_ORIGINS = ['https://shop.example.com']
        PUBLIC_BASE_URL = 'https://shop.example.com'
        _db_url = ''

    with pytest.raises(RuntimeError, match='SMS_PROVIDER 尚未实现'):
        Config.validate()
    Config.SMS_PROVIDER = 'http'
    Config.SMS_HTTP_URL = 'http://sms.example.test/send'
    with pytest.raises(RuntimeError, match='HTTPS'):
        Config.validate()
    Config.SMS_HTTP_URL = 'https://sms.example.test:invalid/send'
    with pytest.raises(RuntimeError, match='SMS_HTTP_URL'):
        Config.validate()
    Config.SMS_HTTP_URL = 'https://sms.example.test/send'
    Config.validate()


def test_production_validates_effective_database_url_without_leaking_secrets(monkeypatch):
    monkeypatch.setenv('PRIVATE_DEPLOY', '0')

    class Config(ProductionConfig):
        SECRET_KEY = 'x' * 48
        ALLOW_MOCK_PAY = False
        SMS_DEV_MODE = False
        SMS_PROVIDER = 'http'
        SMS_HTTP_URL = 'https://sms.example.test/send'
        PLATFORM_BOOTSTRAP_KEY = 'p' * 32
        CORS_ORIGINS = ['https://shop.example.com']
        PUBLIC_BASE_URL = 'https://shop.example.com'

    for uri in ('mysql+pymysql://shop:weak@db/shop', 'sqlite:///shop.sqlite',
                'mysql+pymysql://shop:very-strong-password@db/shop?password=weak',
                'not-a-database-url-SECRET-EXAMPLE'):
        Config.SQLALCHEMY_DATABASE_URI = uri
        with pytest.raises(RuntimeError) as error:
            Config.validate()
        assert '数据库' in str(error.value) or 'DATABASE_URL' in str(error.value)
        assert 'SECRET-EXAMPLE' not in str(error.value)

    Config.SQLALCHEMY_DATABASE_URI = 'mysql+pymysql://shop:strong%40secret%3Apassword@db/shop'
    Config.validate()


def test_create_app_develop_ok(monkeypatch, tmp_path):
    from config import DevelopmentConfig
    from flask_shop import create_app
    monkeypatch.setattr(DevelopmentConfig, 'SQLALCHEMY_DATABASE_URI', f'sqlite:///{tmp_path / "develop-test.sqlite"}')
    monkeypatch.setattr(DevelopmentConfig, 'ORDER_PENDING_TIMEOUT_MINUTES', 0)
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
