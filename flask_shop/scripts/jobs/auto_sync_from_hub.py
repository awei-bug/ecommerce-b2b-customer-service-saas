"""Run the opt-in demo synchronizer as a separate supervised process."""
import json
import hashlib
import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from flask_shop import create_app, db  # noqa: E402
from flask_shop.utils.hub_auto_sync import record_cycle, run_once  # noqa: E402
from flask_shop.utils.hub_client import HubError  # noqa: E402


def acquire_local_lock(app):
    identity = f"{app.config['SQLALCHEMY_DATABASE_URI']}|{app.config.get('DATA_HUB_TENANT_SLUG', '')}"
    name = 'shop-hub-sync-' + hashlib.sha256(identity.encode()).hexdigest() + '.lock'
    handle = open(os.path.join(tempfile.gettempdir(), name), 'a+b')
    handle.seek(0, os.SEEK_END)
    if handle.tell() == 0:
        handle.write(b'0')
        handle.flush()
    handle.seek(0)
    try:
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return None
    return handle


def main():
    if os.getenv('DATA_HUB_AUTO_SYNC_ENABLED', '').lower() not in ('1', 'true', 'yes'):
        print('自动同步未启用；设置 DATA_HUB_AUTO_SYNC_ENABLED=1 后单独启动。', flush=True)
        return 0
    interval = max(30, int(os.getenv('DATA_HUB_AUTO_SYNC_INTERVAL_SECONDS', '300')))
    app = create_app(os.getenv('FLASK_CONFIG', 'develop'), initialize_schema=False, start_background=False)
    lock = acquire_local_lock(app)
    if lock is None:
        print('同一数据库和租户的自动同步进程已在运行。', flush=True)
        return 1
    while True:
        try:
            with app.app_context():
                try:
                    result = run_once()
                    record_cycle(result)
                    print(json.dumps({'event': 'hub_auto_sync', **result}, ensure_ascii=False), flush=True)
                finally:
                    db.session.remove()
        except Exception as exc:
            # Do not print URLs, credentials or database errors; retry next cycle.
            print(json.dumps({'event': 'hub_auto_sync_failed', 'error_type': type(exc).__name__}), flush=True)
            try:
                with app.app_context():
                    failure_code = 'hub_unavailable' if isinstance(exc, HubError) else 'invalid_config' if isinstance(exc, ValueError) else 'other'
                    record_cycle(failed=True, failure_code=failure_code)
                    db.session.remove()
            except Exception:
                app.logger.error('hub auto sync failure record unavailable')
        time.sleep(interval)


if __name__ == '__main__':
    sys.exit(main())
