# -*- coding: utf-8 -*-
"""电商平台配置。"""
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def _env_bool(name, default='0'):
    return os.getenv(name, default).strip().lower() in ('1', 'true', 'yes', 'on')


def _env_list(name, default=''):
    raw = os.getenv(name, default) or ''
    return [x.strip() for x in raw.split(',') if x.strip()]


class Config:
    MYSQL_DIALECT = 'mysql'
    MYSQL_DRIVER = 'pymysql'
    MYSQL_USERNAME = os.getenv('MYSQL_USERNAME', 'root')
    MYSQL_PASSWORD = os.getenv('MYSQL_PASSWORD', '123')
    MYSQL_HOST = os.getenv('MYSQL_HOST', '127.0.0.1')
    MYSQL_PORT = int(os.getenv('MYSQL_PORT', '3306'))
    MYSQL_DB = os.getenv('MYSQL_DB', 'flask_shop')
    MYSQL_CHARSET = 'utf8mb4'

    _db_url = os.getenv('DATABASE_URL', '').strip()
    if _db_url:
        SQLALCHEMY_DATABASE_URI = _db_url
    else:
        SQLALCHEMY_DATABASE_URI = (
            f'{MYSQL_DIALECT}+{MYSQL_DRIVER}://{MYSQL_USERNAME}:{MYSQL_PASSWORD}'
            f'@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DB}?charset={MYSQL_CHARSET}'
        )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-only-secret-key-change-in-production')
    JSON_AS_ASCII = False
    RESTFUL_JSON = {'ensure_ascii': False}
    JWT_EXPIRATION_DELTA = int(os.getenv('JWT_EXPIRATION_DELTA', str(60 * 60 * 24)))

    CORS_ORIGINS = _env_list(
        'CORS_ORIGINS',
        'http://localhost:8080,http://127.0.0.1:8080,http://localhost:8081,http://127.0.0.1:8081,http://localhost:5173,http://127.0.0.1:5173',
    )

    COMPANY_SHORT_NAME = os.getenv('COMPANY_SHORT_NAME', '云购商城')
    DEFAULT_TENANT_SLUG = os.getenv('DEFAULT_TENANT_SLUG', 'demo')
    DEFAULT_TENANT_NAME = os.getenv('DEFAULT_TENANT_NAME', '演示旗舰店')

    ALLOW_MOCK_PAY = _env_bool('ALLOW_MOCK_PAY', '1')
    SMS_DEV_MODE = _env_bool('SMS_DEV_MODE', '1')
    SMS_DEV_CODE = os.getenv('SMS_DEV_CODE', '123456')
    SMS_DEV_COOLDOWN = int(os.getenv('SMS_DEV_COOLDOWN', '10'))
    SMS_COOLDOWN = int(os.getenv('SMS_COOLDOWN', '60'))
    SMS_PROVIDER = os.getenv('SMS_PROVIDER', 'console')
    SMS_HTTP_URL = os.getenv('SMS_HTTP_URL', '')
    SMS_HTTP_TOKEN = os.getenv('SMS_HTTP_TOKEN', '')
    SMS_CODE_EXPIRE_MINUTES = int(os.getenv('SMS_CODE_EXPIRE_MINUTES', '10'))
    PAY_DEFAULT_CHANNEL = os.getenv('PAY_DEFAULT_CHANNEL', 'mock')
    PLATFORM_BOOTSTRAP_KEY = os.getenv('PLATFORM_BOOTSTRAP_KEY', '')
    PUBLIC_BASE_URL = os.getenv('PUBLIC_BASE_URL', 'http://127.0.0.1:5000')
    CONTENT_PLATFORM_CONVERSION_WEBHOOK = os.getenv('CONTENT_PLATFORM_CONVERSION_WEBHOOK', '')
    CONTENT_PLATFORM_WEBHOOK_TOKEN = os.getenv('CONTENT_PLATFORM_WEBHOOK_TOKEN', '')
    # 内容平台直推成品包：'slug1:token1,slug2:token2'，为空则关闭该通道
    INTEGRATION_TOKENS = os.getenv('INTEGRATION_TOKENS', '')
    # 单次直推允许的最大商品数，防止一次灌爆库存/配额
    INTEGRATION_MAX_PRODUCTS = int(os.getenv('INTEGRATION_MAX_PRODUCTS', '200'))
    # 商品知识数据中心：内容平台写入，电商侧拉取上架与客服检索
    DATA_HUB_URL = os.getenv('DATA_HUB_URL', '')
    DATA_HUB_TOKEN = os.getenv('DATA_HUB_TOKEN', '')
    DATA_HUB_TENANT_SLUG = os.getenv('DATA_HUB_TENANT_SLUG', '')
    DATA_HUB_TIMEOUT = int(os.getenv('DATA_HUB_TIMEOUT', '10'))
    # 同步时是否把图片落到本地 static（默认直接用内容平台 URL）
    DATA_HUB_FETCH_IMAGES = _env_bool('DATA_HUB_FETCH_IMAGES', '0')
    TENANT_STRICT = _env_bool('TENANT_STRICT', '0')
    MAX_UPLOAD_IMAGE_BYTES = int(os.getenv('MAX_UPLOAD_IMAGE_BYTES', str(5 * 1024 * 1024)))
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    # 待支付订单超时（分钟）；0 表示关闭自动关单
    ORDER_PENDING_TIMEOUT_MINUTES = int(os.getenv('ORDER_PENDING_TIMEOUT_MINUTES', '30'))
    SUPPORT_BASELINE_MINUTES = int(os.getenv('SUPPORT_BASELINE_MINUTES', '6'))
    LOGIN_ACCOUNT_FAILURE_LIMIT = int(os.getenv('LOGIN_ACCOUNT_FAILURE_LIMIT', '5'))
    LOGIN_IP_FAILURE_LIMIT = int(os.getenv('LOGIN_IP_FAILURE_LIMIT', '20'))
    LOGIN_LOCK_MINUTES = int(os.getenv('LOGIN_LOCK_MINUTES', '15'))

    # Agnes AI 多模态网关（密钥只放服务端环境变量）
    AGNES_ENABLED = _env_bool('AGNES_ENABLED', '1')
    AGNES_BASE_URL = os.getenv('AGNES_BASE_URL', 'https://apihub.agnes-ai.com/v1')
    AGNES_TEXT_MODEL = os.getenv('AGNES_TEXT_MODEL', 'agnes-3.0-flash')
    AGNES_IMAGE_MODEL = os.getenv('AGNES_IMAGE_MODEL', 'agnes-image-2.5-flash')
    AGNES_VIDEO_MODEL = os.getenv('AGNES_VIDEO_MODEL', 'agnes-video-2.5-flash')

    WEAK_SECRETS = frozenset({
        '',
        'dev-only-secret-key-change-in-production',
        'change-me-to-a-long-random-string',
        'secret',
        '123456',
    })


class DevelopmentConfig(Config):
    DEBUG = True
    ALLOW_MOCK_PAY = True
    SMS_DEV_MODE = _env_bool('SMS_DEV_MODE', '1')


class ProductionConfig(Config):
    DEBUG = False
    ALLOW_MOCK_PAY = _env_bool('ALLOW_MOCK_PAY', '0')
    SMS_DEV_MODE = _env_bool('SMS_DEV_MODE', '0')

    @classmethod
    def validate(cls):
        errors = []
        secret = cls.SECRET_KEY or ''
        if secret in cls.WEAK_SECRETS or len(secret) < 32:
            errors.append('生产环境必须设置长度>=32 的随机 SECRET_KEY')
        if '*' in (cls.CORS_ORIGINS or []):
            errors.append('生产环境必须配置明确的 CORS_ORIGINS 白名单（禁止 *）')
        if (not cls.CORS_ORIGINS) and not (_env_bool('PRIVATE_DEPLOY', '0')):
            errors.append('生产环境必须配置 CORS_ORIGINS，或设置 PRIVATE_DEPLOY=1（同域反代/内网）')
        if cls.ALLOW_MOCK_PAY:
            errors.append('生产环境必须 ALLOW_MOCK_PAY=0（禁止模拟支付对外成功）')
        if cls.SMS_DEV_MODE:
            errors.append('生产环境必须 SMS_DEV_MODE=0（禁止固定验证码）')
        pub = (cls.PUBLIC_BASE_URL or '').lower()
        allow_local = _env_bool('PRIVATE_DEPLOY', '0') or _env_bool('ALLOW_LOCALHOST_PUBLIC_URL', '0')
        if (not allow_local) and ('localhost' in pub or '127.0.0.1' in pub):
            errors.append('生产环境 PUBLIC_BASE_URL 不应为 localhost（内网私有化可设 PRIVATE_DEPLOY=1）')
        if not (cls.CORS_ORIGINS or []) and not allow_local:
            # 空 CORS 在同域 Nginx 反代时尚可；裸 API 对外时必须配
            pass
        if not cls._db_url:
            db_password = cls.MYSQL_PASSWORD or ''
            if db_password in ('', '123', 'change-me', 'change-me-db-password', 'root-change-me') or len(db_password) < 12:
                errors.append('生产环境必须设置长度>=12的数据库密码')
        if not cls.SMS_DEV_MODE:
            provider = (cls.SMS_PROVIDER or '').strip().lower()
            if provider in ('', 'console', 'log', 'stdout'):
                errors.append('生产环境必须配置真实 SMS_PROVIDER（不能使用 console）')
            if provider in ('http', 'webhook', 'custom') and not (cls.SMS_HTTP_URL or '').strip():
                errors.append('SMS_PROVIDER=http 时必须配置 SMS_HTTP_URL')
        if cls.LOGIN_ACCOUNT_FAILURE_LIMIT < 3 or cls.LOGIN_LOCK_MINUTES < 1:
            errors.append('登录防爆破阈值配置不安全')
        key = cls.PLATFORM_BOOTSTRAP_KEY or ''
        if (not key) or key in ('dev-platform-key-change-me',) or len(key) < 16:
            errors.append('生产环境必须设置足够强度的 PLATFORM_BOOTSTRAP_KEY')
        if errors:
            raise RuntimeError('配置校验失败: ' + '; '.join(errors))


class TestConfig(Config):
    DEBUG = True
    TESTING = True
    ALLOW_MOCK_PAY = True
    SMS_DEV_MODE = True
    # 固定测试值，避免本机 shell / .env.prod 污染（如超时 1440 分钟）
    ORDER_PENDING_TIMEOUT_MINUTES = 30
    TENANT_STRICT = False
    SQLALCHEMY_DATABASE_URI = os.getenv('TEST_DATABASE_URL', 'sqlite:///:memory:')


# 兼容旧名
TestingConfig = TestConfig

class SampleConfig(ProductionConfig):
    """本机样板店：接近生产，允许开发验证码便于演示。"""
    DEBUG = False
    TESTING = False
    ALLOW_MOCK_PAY = False
    SMS_DEV_MODE = _env_bool('SMS_DEV_MODE', '1')

    @classmethod
    def validate(cls):
        errors = []
        secret = cls.SECRET_KEY or ''
        if secret in cls.WEAK_SECRETS or len(secret) < 32:
            errors.append('样板店请设置长度>=32 的 SECRET_KEY（deploy/.env.prod）')
        if errors:
            raise RuntimeError('配置校验失败: ' + '; '.join(errors))


config_map = {
    'develop': DevelopmentConfig,
    'product': ProductionConfig,
    'test': TestConfig,
    'sample': SampleConfig,
}
