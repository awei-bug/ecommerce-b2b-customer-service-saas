import importlib.util
import sys
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest


ROOT = Path(__file__).resolve().parents[2]


def load_script(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def manual_restore():
    return load_script("manual_restore_test", ROOT / "deploy" / "win" / "restore_mysql_local.py")


@pytest.fixture
def rehearsal():
    return load_script("rehearsal_test", ROOT / "flask_shop" / "scripts" / "verify" / "rehearse_restore.py")


class FakeCursor:
    def __init__(self, fail_create=False, fail_insert=False):
        self.commands = []
        self.fail_create = fail_create
        self.fail_insert = fail_insert

    def execute(self, statement):
        self.commands.append(statement)
        if self.fail_create and statement.startswith("CREATE DATABASE"):
            raise RuntimeError("database exists")
        if self.fail_insert and statement.startswith("INSERT"):
            raise RuntimeError("broken backup")

    def fetchall(self):
        return [("t_order",)]


class FakeConnection:
    def __init__(self, cursor):
        self.fake_cursor = cursor
        self.closed = False

    def cursor(self):
        return self.fake_cursor

    def close(self):
        self.closed = True


def test_manual_restore_rejects_fixed_database_without_connecting(manual_restore, monkeypatch):
    monkeypatch.setenv("RESTORE_DB", "flask_shop")
    monkeypatch.setattr(manual_restore.pymysql, "connect", lambda **kwargs: pytest.fail("must not connect"))
    assert manual_restore.main() == 1


def test_manual_restore_reports_sql_failure_and_never_drops_database(manual_restore, monkeypatch, tmp_path):
    monkeypatch.delenv("RESTORE_DB", raising=False)
    backup = tmp_path / "backup.sql"
    backup.write_text("SET NAMES utf8mb4;\nINSERT INTO t VALUES (1);\n", encoding="utf-8")
    cursor = FakeCursor(fail_insert=True)
    connection = FakeConnection(cursor)
    monkeypatch.setattr(manual_restore.pymysql, "connect", lambda **kwargs: connection)
    monkeypatch.setattr(sys, "argv", ["restore", str(backup)])
    assert manual_restore.main() == 1
    assert connection.closed
    assert cursor.commands[0].startswith("CREATE DATABASE `shop_restore_")
    assert not any(command.startswith("DROP DATABASE") for command in cursor.commands)


def test_rehearsal_collision_never_deletes_existing_database(rehearsal, monkeypatch, tmp_path):
    backup = tmp_path / "backup.sql"
    backup.write_text("SET NAMES utf8mb4;\n", encoding="utf-8")
    cursor = FakeCursor(fail_create=True)
    monkeypatch.setattr(rehearsal, "_connect", lambda database=None: FakeConnection(cursor))
    with pytest.raises(RuntimeError, match="database exists"):
        rehearsal._restore(backup, "shop_rehearsal_" + "a" * 32)
    assert len(cursor.commands) == 1
    assert cursor.commands[0].startswith("CREATE DATABASE")


def test_rehearsal_rejects_non_generated_database_name(rehearsal, monkeypatch, tmp_path):
    monkeypatch.setattr(rehearsal, "_connect", lambda database=None: pytest.fail("must not connect"))
    with pytest.raises(ValueError, match="临时库"):
        rehearsal._restore(tmp_path / "backup.sql", "flask_shop")


def test_rehearsal_connects_to_the_configured_database_server(rehearsal, monkeypatch):
    monkeypatch.setitem(rehearsal.config_map, "develop", SimpleNamespace(
        SQLALCHEMY_DATABASE_URI="mysql+pymysql://user:p%40ss@db.example:3308/shop?charset=utf8mb4"
    ))
    captured = {}
    monkeypatch.setattr(rehearsal.pymysql, "connect", lambda **kwargs: captured.update(kwargs))
    rehearsal._connect("shop")
    assert captured["host"] == "db.example"
    assert captured["port"] == 3308
    assert captured["password"] == "p@ss"
    assert captured["database"] == "shop"


def test_rehearsal_rejects_unsupported_connection_options(rehearsal, monkeypatch):
    monkeypatch.setitem(rehearsal.config_map, "develop", SimpleNamespace(
        SQLALCHEMY_DATABASE_URI="mysql+pymysql://user:pass@db/shop?unix_socket=/tmp/mysql.sock"
    ))
    with pytest.raises(ValueError, match="未支持"):
        rehearsal._source_url()


def test_backup_escapes_newlines_and_mysql_special_characters():
    with patch.dict(os.environ):
        backup = load_script("local_backup_test", ROOT / "deploy" / "win" / "backup_mysql_local.py")
    escaped = backup.esc("第一行;\n第二行\\'\x00")
    assert "\n" not in escaped
    assert escaped == r"第一行;\n第二行\\\'\0"
