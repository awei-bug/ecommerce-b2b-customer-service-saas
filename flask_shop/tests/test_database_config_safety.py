import importlib.util
import os
import json
import socket
import sqlite3
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import Mock

from sqlalchemy.engine import URL


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / 'flask_shop'


def load_check():
    spec = importlib.util.spec_from_file_location('go_live_check_test', BACKEND / 'scripts' / 'verify' / 'go_live_check.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_mysql_environment_password_special_characters_are_preserved():
    env = os.environ.copy()
    env.pop('DATABASE_URL', None)
    env.update(MYSQL_USERNAME='account@test', MYSQL_PASSWORD='secret@:/?#example',
               MYSQL_HOST='127.0.0.1', MYSQL_PORT='3307', MYSQL_DB='shop_test')
    code = (
        'from config import Config; from sqlalchemy.engine import make_url; '
        'url = make_url(Config.SQLALCHEMY_DATABASE_URI); '
        'print(url.username == "account@test" and url.password == "secret@:/?#example" '
        'and url.host == "127.0.0.1" and url.database == "shop_test")'
    )
    result = subprocess.run([sys.executable, '-c', code], cwd=BACKEND, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'True'
    assert 'secret@' not in result.stdout + result.stderr


def test_dev_launcher_does_not_print_database_url_password():
    env = os.environ.copy()
    env['DATABASE_URL'] = 'mysql+pymysql://user:very-secret-password@host/db?token=secret-query'
    code = (
        'import runpy,sys,types; '
        'm=types.ModuleType("manager"); '
        'm.app=types.SimpleNamespace(run=lambda **kwargs: None); '
        'sys.modules["manager"]=m; '
        'runpy.run_path("run_dev_api.py",run_name="__main__")'
    )
    result = subprocess.run([sys.executable, '-c', code], cwd=BACKEND, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert 'DATABASE_URL override is set' in result.stdout
    assert 'very-secret-password' not in result.stdout + result.stderr
    assert 'secret-query' not in result.stdout + result.stderr


def test_dev_preflight_checks_existing_sqlite_without_creating_missing_database(tmp_path):
    import sqlite3

    script = BACKEND / 'scripts' / 'verify' / 'dev_preflight.py'
    database = tmp_path / 'existing.sqlite'
    with sqlite3.connect(database) as connection:
        connection.execute('CREATE TABLE example (id INTEGER)')
    env = os.environ.copy()
    env.update(DATABASE_URL=f'sqlite:///{database.as_posix()}', MYSQL_HOST='ignored-invalid-host',
               PYTHONIOENCODING='utf-8')
    before = database.read_bytes()
    result = subprocess.run([sys.executable, str(script)], cwd=BACKEND, env=env,
                            capture_output=True, text=True, encoding='utf-8', timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert database.read_bytes() == before
    missing = tmp_path / 'must-not-create.sqlite'
    env['DATABASE_URL'] = f'sqlite:///{missing.as_posix()}'
    result = subprocess.run([sys.executable, str(script)], cwd=BACKEND, env=env,
                            capture_output=True, text=True, encoding='utf-8', timeout=30)
    assert result.returncode == 1
    assert not missing.exists()


def test_dev_preflight_accepts_sqlalchemy_url_object_without_exposing_password(monkeypatch, capsys):
    import sqlalchemy
    from config import Config

    spec = importlib.util.spec_from_file_location('dev_preflight_test', BACKEND / 'scripts' / 'verify' / 'dev_preflight.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, 'configure_development', lambda: None)
    monkeypatch.setattr(Config, 'SQLALCHEMY_DATABASE_URI', URL.create(
        'mysql+pymysql', username='test', password='private-password', host='example', database='shop'))
    engine = Mock()
    connection = Mock()
    engine.connect.return_value.__enter__ = Mock(return_value=connection)
    engine.connect.return_value.__exit__ = Mock(return_value=False)
    factory = Mock(return_value=engine)
    monkeypatch.setattr(sqlalchemy, 'create_engine', factory)
    assert module.main() == 0
    assert factory.call_args.kwargs['connect_args'] == {'connect_timeout': 5}
    assert 'private-password' not in capsys.readouterr().out


def test_dev_api_starts_against_isolated_database_and_serves_health(tmp_path):
    database = tmp_path / 'isolated.sqlite'
    with sqlite3.connect(database):
        pass
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
    env = os.environ.copy()
    env.update(DATABASE_URL=f'sqlite:///{database.as_posix()}', FLASK_PORT=str(port),
               PAY_PROOF_FOLDER=str(tmp_path / 'proofs'), PYTHONIOENCODING='utf-8')
    preflight = subprocess.run([sys.executable, str(BACKEND / 'scripts' / 'verify' / 'dev_preflight.py')],
                               cwd=BACKEND, env=env, capture_output=True, text=True, encoding='utf-8', timeout=30)
    assert preflight.returncode == 0, preflight.stdout + preflight.stderr
    log_path = tmp_path / 'api.log'
    with log_path.open('w', encoding='utf-8') as log:
        process = subprocess.Popen([sys.executable, 'run_dev_api.py'], cwd=BACKEND, env=env,
                                   stdout=log, stderr=subprocess.STDOUT,
                                   creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        try:
            deadline = time.monotonic() + 30
            health = None
            while time.monotonic() < deadline and process.poll() is None:
                try:
                    with urlopen(f'http://127.0.0.1:{port}/health/', timeout=1) as response:
                        health = json.load(response)
                    break
                except (OSError, URLError):
                    time.sleep(0.2)
            if health is None:
                log.flush()
                raise AssertionError(f'API did not start: {log_path.read_text(encoding="utf-8", errors="replace")}')
            assert health['app'] == 'ecommerce-shop'
            with urlopen(f'http://127.0.0.1:{port}/api/c/ping/', timeout=3) as response:
                assert json.load(response)['msg'] == 'c-api ok'
            with sqlite3.connect(database) as connection:
                assert connection.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='t_order'").fetchone()[0] == 1
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)


def test_go_live_database_summary_never_includes_credentials_or_query():
    check = load_check()
    uri = URL.create('mysql+pymysql', username='account', password='secret@password',
                     host='db.example.test', port=3307, database='shop',
                     query={'token': 'secret-query'})
    summary = check.database_summary(uri)
    assert summary == 'mysql+pymysql://db.example.test:3307/shop'
    assert 'account' not in summary and 'secret' not in summary
    assert check.database_summary('not-a-url-secret') == '<invalid database URL>'
    assert check.database_summary('sqlite:///sensitive-path.sqlite') == 'sqlite (path hidden)'


def test_go_live_production_requires_an_explicit_store_without_changing_db_env(monkeypatch, capsys):
    check = load_check()
    secret_url = 'mysql+pymysql://user:some-secret-password@db/real_shop'
    monkeypatch.setenv('FLASK_CONFIG', 'product')
    monkeypatch.setenv('DATABASE_URL', secret_url)
    monkeypatch.delenv('GO_LIVE_TENANT_SLUG', raising=False)
    monkeypatch.setattr(check.os, 'chdir', lambda path: None)
    monkeypatch.setattr(check, 'load_dotenv', lambda *args, **kwargs: None)
    monkeypatch.setattr(sys, 'argv', ['go_live_check.py'])
    assert check.main() == 1
    assert os.environ['DATABASE_URL'] == secret_url
    output = capsys.readouterr().out
    assert '--tenant' in output
    assert 'some-secret-password' not in output


def test_read_only_app_creation_skips_schema_changes_and_background_tasks(monkeypatch, tmp_path):
    import flask_shop
    from config import DevelopmentConfig
    from flask_shop.utils import order_timeout

    monkeypatch.setattr(DevelopmentConfig, 'SQLALCHEMY_DATABASE_URI', f'sqlite:///{tmp_path / "check.sqlite"}')
    schema = Mock()
    background = Mock()
    monkeypatch.setattr(flask_shop, 'ensure_schema_compat', schema)
    monkeypatch.setattr(order_timeout, 'start_timeout_loop', background)
    app = flask_shop.create_app('develop', initialize_schema=False, start_background=False)
    assert app.config['DEBUG'] is True
    schema.assert_not_called()
    background.assert_not_called()
    assert not (tmp_path / 'check.sqlite').exists()


def test_schema_compat_never_modifies_existing_column_definitions(monkeypatch):
    import flask_shop

    session = Mock()
    database = Mock(session=session)
    monkeypatch.setattr(flask_shop, 'db', database)
    app = Mock()
    app.app_context.return_value = nullcontext()

    flask_shop.ensure_schema_compat(app)

    statements = [str(call.args[0]).upper() for call in session.execute.call_args_list]
    assert statements
    assert all('MODIFY COLUMN' not in statement for statement in statements)
    assert any('ADD COLUMN' in statement for statement in statements)
    database.create_all.assert_called_once()


def test_migration_runner_invokes_entry_and_rejects_failure(tmp_path):
    import pytest

    spec = importlib.util.spec_from_file_location(
        'migration_runner_test', BACKEND / 'scripts' / 'migrations' / 'run_migrations.py',
    )
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    marker = tmp_path / 'called'
    script = tmp_path / 'migration.py'
    script.write_text(f'def main():\n    open({str(marker)!r}, "w").write("called")\n    return 3\n', encoding='utf-8')
    with pytest.raises(runner.MigrationError, match='非零'):
        runner._run_one(script)
    assert marker.read_text() == 'called'


def test_migration_runner_fails_closed_without_connecting_to_database(tmp_path):
    database = tmp_path / 'must-not-be-created.sqlite'
    env = os.environ.copy()
    env.update(FLASK_CONFIG='develop', DATABASE_URL=f'sqlite:///{database}', PYTHONIOENCODING='utf-8')
    script = BACKEND / 'scripts' / 'migrations' / 'run_migrations.py'
    for args, expected in [([], 2), (['--force'], 2), (['--only', 'migrate_sku'], 2), (['--dry-run'], 0)]:
        result = subprocess.run([sys.executable, str(script), *args], cwd=BACKEND, env=env,
                                capture_output=True, text=True, encoding='utf-8', timeout=30)
        assert result.returncode == expected, result.stdout + result.stderr
        assert not database.exists()


def test_go_live_check_uses_explicit_database_and_store_without_schema_changes(app):
    from flask_shop import db, models
    user = models.User.query.filter_by(tenant_id=app._seed_ctx['id_a']).first()
    user.password = 'strong-test-password'
    db.session.commit()
    env = os.environ.copy()
    env.update(FLASK_CONFIG='develop', DATABASE_URL=str(app.config['SQLALCHEMY_DATABASE_URI']),
               SECRET_KEY='a-strong-test-only-secret-key-value', PYTHONIOENCODING='utf-8')
    result = subprocess.run(
        [sys.executable, str(BACKEND / 'scripts' / 'verify' / 'go_live_check.py'), '--tenant', 'test-a'],
        cwd=BACKEND, env=env, capture_output=True, text=True, encoding='utf-8', timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert 'db:     sqlite (path hidden)' in result.stdout
    assert 'tenant: 测试租户A' in result.stdout
    assert '当前不是生产配置' in result.stdout
    assert str(app.config['SQLALCHEMY_DATABASE_URI']) not in result.stdout


def test_go_live_check_warns_when_platform_api_is_enabled(app):
    from flask_shop import db, models
    user = models.User.query.filter_by(tenant_id=app._seed_ctx['id_a']).first()
    user.password = 'strong-test-password'
    db.session.commit()
    env = os.environ.copy()
    env.update(FLASK_CONFIG='develop', DATABASE_URL=str(app.config['SQLALCHEMY_DATABASE_URI']),
               SECRET_KEY='a-strong-test-only-secret-key-value', PYTHONIOENCODING='utf-8',
               PLATFORM_API_ENABLED='1')
    result = subprocess.run(
        [sys.executable, str(BACKEND / 'scripts' / 'verify' / 'go_live_check.py'), '--tenant', 'test-a'],
        cwd=BACKEND, env=env, capture_output=True, text=True, encoding='utf-8', timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert '平台管理接口已启用' in result.stdout


def test_go_live_check_blocks_default_password_for_any_staff_in_selected_tenant(app):
    env = os.environ.copy()
    env.update(FLASK_CONFIG='develop', DATABASE_URL=str(app.config['SQLALCHEMY_DATABASE_URI']),
               SECRET_KEY='a-strong-test-only-secret-key-value', PYTHONIOENCODING='utf-8')
    result = subprocess.run(
        [sys.executable, str(BACKEND / 'scripts' / 'verify' / 'go_live_check.py'), '--tenant', 'test-a'],
        cwd=BACKEND, env=env, capture_output=True, text=True, encoding='utf-8', timeout=30,
    )
    assert result.returncode == 1
    assert '本店员工存在默认密码' in result.stdout
    assert 'admin_a' not in result.stdout


def test_schema_audit_reports_missing_tables_columns_and_inexact_mysql_amounts(monkeypatch):
    from sqlalchemy import Column, Float, Integer, MetaData, Numeric, Table

    from flask_shop.utils import schema_audit
    metadata = MetaData()
    Table('orders', metadata, Column('id', Integer), Column('amount', Numeric(12, 2)), Column('status', Integer))
    Table('other', metadata, Column('id', Integer))
    inspector = Mock()
    inspector.get_table_names.return_value = ['orders']
    inspector.get_columns.return_value = [
        {'name': 'id', 'type': Integer()}, {'name': 'amount', 'type': Float()},
    ]
    engine = Mock()
    engine.dialect.name = 'mysql'
    monkeypatch.setattr(schema_audit, 'inspect', lambda unused: inspector)
    problems = schema_audit.schema_problems(engine, metadata)
    assert any('缺少表 other' in problem for problem in problems)
    assert any('缺少列 orders.status' in problem for problem in problems)
    assert any('数值类型不匹配 orders.amount' in problem for problem in problems)
    inspector.get_columns.return_value[1]['type'] = Numeric(12, 2)
    assert not any('数值类型不匹配' in problem for problem in schema_audit.schema_problems(engine, metadata))
    inspector.get_columns.return_value[1]['type'] = Numeric(10, 2)
    assert any('数值类型不匹配' in problem for problem in schema_audit.schema_problems(engine, metadata))


def test_go_live_check_blocks_incomplete_schema_without_writing(tmp_path):
    import sqlite3

    database = tmp_path / 'incomplete.sqlite'
    with sqlite3.connect(database) as connection:
        connection.execute('CREATE TABLE t_tenants (id INTEGER PRIMARY KEY)')
    before = database.read_bytes()
    env = os.environ.copy()
    env.update(FLASK_CONFIG='develop', DATABASE_URL=f'sqlite:///{database}',
               SECRET_KEY='a-strong-test-only-secret-key-value', PYTHONIOENCODING='utf-8')
    result = subprocess.run(
        [sys.executable, str(BACKEND / 'scripts' / 'verify' / 'go_live_check.py'), '--tenant', 'test-a'],
        cwd=BACKEND, env=env, capture_output=True, text=True, encoding='utf-8', timeout=30,
    )
    assert result.returncode == 1
    assert '缺少列 t_tenants.' in result.stdout
    assert '缺少表' in result.stdout
    assert database.read_bytes() == before


def test_production_startup_checks_schema_without_automatic_ddl(monkeypatch, tmp_path):
    import pytest
    import flask_shop
    from config import ProductionConfig

    database = tmp_path / 'production-test.sqlite'
    monkeypatch.setattr(ProductionConfig, 'SQLALCHEMY_DATABASE_URI', f'sqlite:///{database.as_posix()}')
    monkeypatch.setattr(ProductionConfig, 'validate', classmethod(lambda cls: None))
    schema_init = Mock()
    monkeypatch.setattr(flask_shop, 'ensure_schema_compat', schema_init)
    with pytest.raises(RuntimeError, match='生产启动不会自动修改数据库'):
        flask_shop.create_app('product', start_background=False)
    schema_init.assert_not_called()
    app = flask_shop.create_app('product', initialize_schema=False, start_background=False)
    with app.app_context():
        flask_shop.db.create_all()
    flask_shop.create_app('product', start_background=False)
    schema_init.assert_not_called()


def test_empty_schema_initializer_requires_confirmation_and_refuses_existing_schema(tmp_path):
    database = tmp_path / 'empty.sqlite'
    database_name = database.as_posix()
    script = BACKEND / 'scripts' / 'migrations' / 'init_empty_schema.py'
    env = os.environ.copy()
    env.update(FLASK_CONFIG='develop', DATABASE_URL=f'sqlite:///{database_name}', PYTHONIOENCODING='utf-8')

    def run(name):
        return subprocess.run([sys.executable, str(script), '--confirm-database', name], cwd=BACKEND,
                              env=env, capture_output=True, text=True, encoding='utf-8', timeout=30)

    assert run('wrong-database').returncode == 2
    assert not database.exists()
    assert run(database_name).returncode == 0
    before = database.read_bytes()
    result = run(database_name)
    assert result.returncode == 2
    assert '已有表或视图' in result.stdout
    assert database.read_bytes() == before
