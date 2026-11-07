"""Check development dependencies and the configured database without initializing schema."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from dev_runtime import configure_development


def main():
    configure_development()
    try:
        from PIL import Image
        from sqlalchemy import create_engine, text
        from sqlalchemy.engine import make_url
        from config import Config

        url = make_url(Config.SQLALCHEMY_DATABASE_URI)
        if url.get_backend_name() == 'sqlite':
            if not url.database or url.database == ':memory:' or not os.path.isfile(url.database):
                print('SQLite 数据库文件不存在或不是持久数据库；不会自动创建。')
                return 1
        engine = create_engine(url, connect_args={'connect_timeout': 5} if url.get_backend_name() == 'mysql' else {})
        try:
            with engine.connect() as connection:
                connection.execute(text('SELECT 1'))
        finally:
            engine.dispose()
    except ImportError:
        print(r'后端依赖缺失，请在 flask_shop 目录运行 .venv\Scripts\python.exe -m pip install -r requirements.txt')
        return 1
    except Exception:
        print('数据库连接检查失败，请核对开发配置和数据库服务；未输出连接凭据。')
        return 1
    print('后端依赖和数据库连接检查通过。')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
