import os

# 尝试加载 .env（无 python-dotenv 时静默跳过）
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


class Config:
    MYSQL_DIALECT = 'mysql'
    MYSQL_DRIVER = 'pymysql'
    MYSQL_USERNAME = os.getenv('MYSQL_USERNAME', 'root')
    MYSQL_PASSWORD = os.getenv('MYSQL_PASSWORD', '123')
    MYSQL_HOST = os.getenv('MYSQL_HOST', '127.0.0.1')
    MYSQL_PORT = int(os.getenv('MYSQL_PORT', '3306'))
    MYSQL_DB = os.getenv('MYSQL_DB', 'flask_shop_saas')
    MYSQL_CHARSET = 'utf8mb4'

    SQLALCHEMY_DATABASE_URI = (
        f'{MYSQL_DIALECT}+{MYSQL_DRIVER}://{MYSQL_USERNAME}:{MYSQL_PASSWORD}'
        f'@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DB}?charset={MYSQL_CHARSET}'
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # 固定密钥：必须来自环境变量，禁止 os.urandom（否则重启后全部 token 失效）
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-only-secret-key-change-in-production')

    JSON_AS_ASCII = False
    RESTFUL_JSON = {'ensure_ascii': False}

    JWT_EXPIRATION_DELTA = int(os.getenv('JWT_EXPIRATION_DELTA', str(60 * 60 * 24)))

    ALLOWED_EXTENSIONS = ['jpg', 'jpeg', 'png', 'gif']
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'flask_shop', 'static', 'upload')

    # ---- 支付 ----
    # mock | wechat；生产建议 wechat，且 ALLOW_MOCK_PAY=0
    PAY_DEFAULT_CHANNEL = os.getenv('PAY_DEFAULT_CHANNEL', 'mock').lower()
    ALLOW_MOCK_PAY = os.getenv('ALLOW_MOCK_PAY', '1') == '1'

    # 微信直连商户（密钥勿提交仓库，只放 .env / 服务器环境变量）
    WECHAT_MCH_ID = os.getenv('WECHAT_MCH_ID', '')
    WECHAT_MCH_SERIAL_NO = os.getenv('WECHAT_MCH_SERIAL_NO', '')
    WECHAT_MCH_PRIVATE_KEY_PATH = os.getenv('WECHAT_MCH_PRIVATE_KEY_PATH', '')
    WECHAT_APP_ID = os.getenv('WECHAT_APP_ID', '')
    WECHAT_API_V3_KEY = os.getenv('WECHAT_API_V3_KEY', '')
    WECHAT_NOTIFY_URL = os.getenv('WECHAT_NOTIFY_URL', '')
    WECHAT_PAY_TRADE_TYPE = os.getenv('WECHAT_PAY_TRADE_TYPE', 'native')  # native|h5|jsapi
    # 平台证书缓存目录（wechatpayv3 自动下载）
    WECHAT_CERT_DIR = os.getenv(
        'WECHAT_CERT_DIR',
        os.path.join(os.path.dirname(os.path.abspath(__file__)), '.wechat_certs'),
    )
    # JSAPI 可配置默认 openid；生产应由用户微信授权获得
    WECHAT_PAYER_OPENID = os.getenv('WECHAT_PAYER_OPENID', '')

    # ---- C 端短信登录（骨架）----
    # 开发默认打开：固定验证码，发送接口可返回 dev_code
    SMS_DEV_MODE = os.getenv('SMS_DEV_MODE', '1') == '1'
    SMS_DEV_CODE = os.getenv('SMS_DEV_CODE', '123456')
    SMS_CODE_EXPIRE_MINUTES = int(os.getenv('SMS_CODE_EXPIRE_MINUTES', '10'))


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False
    # 私有化无官方支付：默认不走自动 mock 成功；channel 可用 mock 占位，收款靠「标记已付款」
    ALLOW_MOCK_PAY = os.getenv('ALLOW_MOCK_PAY', '0') == '1'
    PAY_DEFAULT_CHANNEL = os.getenv('PAY_DEFAULT_CHANNEL', 'mock').lower()
    SMS_DEV_MODE = os.getenv('SMS_DEV_MODE', '0') == '1'

    @classmethod
    def validate(cls):
        if cls.SECRET_KEY in (None, '', 'dev-only-secret-key-change-in-production', 'change-me-to-a-long-random-string'):
            raise RuntimeError('生产环境必须设置足够长的随机 SECRET_KEY')
        if cls.ALLOW_MOCK_PAY:
            # 允许启动但强烈不推荐；打日志由应用侧处理
            pass
        if cls.PAY_DEFAULT_CHANNEL == 'wechat':
            # 仅检查是否误开 wechat 却无任何配置（不强制，避免未配证书无法启动）
            pass


class TestingConfig(Config):
    TESTING = True
    MYSQL_DB = os.getenv('MYSQL_DB', 'flask_shop_saas_test')
    ALLOW_MOCK_PAY = True
    PAY_DEFAULT_CHANNEL = 'mock'


config_map = {
    'develop': DevelopmentConfig,
    'product': ProductionConfig,
    'test': TestingConfig,
}
