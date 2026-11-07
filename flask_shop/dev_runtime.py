import os
from pathlib import Path


def configure_development():
    for key in (
        'FLASK_CONFIG', 'FLASK_ENV', 'ALLOW_MOCK_PAY', 'SMS_DEV_MODE', 'PRIVATE_DEPLOY',
        'PLATFORM_BOOTSTRAP_KEY', 'PUBLIC_BASE_URL', 'PAY_DEFAULT_CHANNEL',
        'ORDER_PENDING_TIMEOUT_MINUTES', 'SECRET_KEY', 'MYSQL_HOST', 'MYSQL_PASSWORD',
        'MYSQL_ROOT_PASSWORD', 'MYSQL_DB', 'MYSQL_USERNAME',
    ):
        os.environ.pop(key, None)
    os.environ['FLASK_CONFIG'] = 'develop'
    os.environ['FLASK_ENV'] = 'develop'
    os.environ['ALLOW_MOCK_PAY'] = '1'
    os.environ['SMS_DEV_MODE'] = '1'
    os.environ['SMS_DEV_CODE'] = '123456'
    os.chdir(Path(__file__).resolve().parent)
