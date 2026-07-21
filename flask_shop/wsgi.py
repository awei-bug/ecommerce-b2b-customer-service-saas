"""
生产 WSGI 入口。
用法：gunicorn -c deploy/gunicorn.conf.py "wsgi:app"
"""
import os

from flask_cors import CORS
from flask_migrate import Migrate

# 必须在 create_app 前设置（.env 里也可写 FLASK_CONFIG=product）
os.environ.setdefault('FLASK_CONFIG', os.getenv('FLASK_CONFIG', 'product'))

from flask_shop import create_app, db  # noqa: E402
from config import config_map  # noqa: E402

_config_name = os.getenv('FLASK_CONFIG', 'product')
if _config_name not in config_map:
    _config_name = 'product'

app = create_app(_config_name)

# 生产 CORS：用环境变量逗号分隔源；空则允许同域（仅 API 被 Nginx 反代时前端可不跨域）
_cors = os.getenv('CORS_ORIGINS', '').strip()
if _cors:
    origins = [o.strip() for o in _cors.split(',') if o.strip()]
    CORS(app, resources={r"/*": {"origins": origins}}, supports_credentials=True)
else:
    # 未配置时仍打开 CORS，便于初期联调；上线后请设置 CORS_ORIGINS
    CORS(app, supports_credentials=True)

Migrate(app, db)

# 生产配置校验（SECRET_KEY 等）
cfg = config_map.get(_config_name)
if cfg and hasattr(cfg, 'validate'):
    try:
        cfg.validate()
    except Exception as e:
        # 启动期打印，避免静默用弱密钥
        app.logger.error('Production config validation failed: %s', e)
        raise
