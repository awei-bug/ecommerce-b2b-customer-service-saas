import gzip
import importlib.util
import os
import shutil
import subprocess
import tarfile
import time
from pathlib import Path
from unittest.mock import patch

import pytest


ROOT = Path(__file__).resolve().parents[2]
BASH = shutil.which("bash")


def run_backup(tmp_path, script, *, method="local"):
    env = os.environ.copy()
    env.update({
        "MYSQL_BACKUP_METHOD": method,
        "MYSQL_DB": "backup_test",
        "MYSQL_PASSWORD": "test-password-not-for-logs",
        "BACKUP_KEEP_DAYS": "7",
    })
    command = r'''set -eu
fake="$1"
out="$2"
script="$3"
if command -v cygpath >/dev/null 2>&1; then
  fake="$(cygpath -u "$fake")"
  out="$(cygpath -u "$out")"
  script="$(cygpath -u "$script")"
fi
export PATH="$fake:$PATH" BACKUP_DIR="$out"
bash "$script"
'''
    return subprocess.run(
        [BASH, "-c", command, "backup-test", str(tmp_path / "bin"),
         str(tmp_path / "backups"), str(script)],
        env=env, capture_output=True, text=True,
    )


@pytest.mark.skipif(not BASH, reason="bash is required")
def test_mysql_backup_only_publishes_successful_nonempty_dumps(tmp_path):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    executable = fake_bin / "mysqldump"
    executable.write_text("#!/usr/bin/env bash\nprintf 'CREATE TABLE t (id int);\n'\n", encoding="utf-8")
    executable.chmod(0o755)
    script = ROOT / "deploy" / "backup_mysql.sh"
    first = run_backup(tmp_path, script)
    assert first.returncode == 0, first.stderr
    backups = list((tmp_path / "backups").glob("*.sql.gz"))
    assert len(backups) == 1
    assert gzip.open(backups[0], "rt").read() == "CREATE TABLE t (id int);\n"
    assert "test-password-not-for-logs" not in first.stdout + first.stderr

    executable.write_text("#!/usr/bin/env bash\nprintf 'incomplete'\nexit 1\n", encoding="utf-8")
    failed = run_backup(tmp_path, script)
    assert failed.returncode != 0
    assert list((tmp_path / "backups").glob("*.sql.gz")) == backups
    assert not list((tmp_path / "backups").glob("*.partial.*"))

    executable.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    empty = run_backup(tmp_path, script)
    assert empty.returncode != 0
    assert list((tmp_path / "backups").glob("*.sql.gz")) == backups
    assert not list((tmp_path / "backups").glob("*.partial.*"))


@pytest.mark.skipif(not BASH, reason="bash is required")
def test_docker_backup_uses_explicit_method_and_passes_password_via_environment(tmp_path):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    executable = fake_bin / "docker"
    executable.write_text(
        "#!/usr/bin/env bash\n"
        "[ \"$1\" = exec ] && [ \"$2\" = -e ] && [ \"$3\" = MYSQL_PWD ] || exit 4\n"
        "[ \"$MYSQL_PWD\" = test-password-not-for-logs ] || exit 5\n"
        "printf 'CREATE TABLE t (id int);\n'\n",
        encoding="utf-8",
    )
    executable.chmod(0o755)
    result = run_backup(tmp_path, ROOT / "deploy" / "backup_mysql.sh", method="docker")
    assert result.returncode == 0, result.stderr
    assert len(list((tmp_path / "backups").glob("*.sql.gz"))) == 1
    assert "test-password-not-for-logs" not in result.stdout + result.stderr


@pytest.mark.skipif(not BASH, reason="bash is required")
def test_full_docker_backup_reads_container_uploads_and_fails_if_unavailable(tmp_path, monkeypatch):
    fake_bin = tmp_path / 'bin'
    fake_bin.mkdir()
    upload = tmp_path / 'fixture' / 'upload'
    upload.mkdir(parents=True)
    (upload / 'proof.txt').write_text('container-only-data', encoding='utf-8')
    proofs = upload.parent / 'pay_proofs'
    proofs.mkdir()
    (proofs / 'private.txt').write_text('private-data', encoding='utf-8')
    monkeypatch.setenv('FAKE_UPLOAD_PARENT', str(upload.parent))
    executable = fake_bin / 'docker'
    executable.write_text(
        '#!/usr/bin/env bash\n'
        'if [ "$2" = "-e" ]; then printf "CREATE TABLE t (id int);\n"; exit 0; fi\n'
        '[ "$2" = "shop_api" ] || exit 7\n'
        '[ "${FAKE_FAIL_UPLOAD:-0}" != 1 ] || exit 9\n'
        'folder="$FAKE_UPLOAD_PARENT"\n'
        'if command -v cygpath >/dev/null 2>&1; then folder="$(cygpath -u "$folder")"; fi\n'
        'case "${@: -1}" in */pay_proofs) dir=pay_proofs ;; *) dir=upload ;; esac\n'
        '[ "$dir" != pay_proofs ] || [ "${FAKE_FAIL_PROOFS:-0}" != 1 ] || exit 8\n'
        'tar -czf - -C "$folder" "$dir"\n', encoding='utf-8',
    )
    executable.chmod(0o755)
    script = ROOT / 'deploy' / 'backup_all.sh'
    result = run_backup(tmp_path, script, method='docker')
    assert result.returncode == 0, result.stdout + result.stderr
    archives = list((tmp_path / 'backups').glob('uploads_*.tar.gz'))
    assert len(archives) == 1
    with tarfile.open(archives[0], 'r:gz') as archive:
        assert archive.extractfile('upload/proof.txt').read() == b'container-only-data'
    proof_archives = list((tmp_path / 'backups').glob('pay_proofs_*.tar.gz'))
    assert len(proof_archives) == 1
    with tarfile.open(proof_archives[0], 'r:gz') as archive:
        assert archive.extractfile('pay_proofs/private.txt').read() == b'private-data'
    monkeypatch.setenv('FAKE_FAIL_UPLOAD', '1')
    failed = run_backup(tmp_path, script, method='docker')
    assert failed.returncode != 0
    assert list((tmp_path / 'backups').glob('uploads_*.tar.gz')) == archives
    assert not list((tmp_path / 'backups').glob('*.partial.*'))
    monkeypatch.setenv('FAKE_FAIL_UPLOAD', '0')
    monkeypatch.setenv('FAKE_FAIL_PROOFS', '1')
    failed_proofs = run_backup(tmp_path, script, method='docker')
    assert failed_proofs.returncode != 0
    assert list((tmp_path / 'backups').glob('pay_proofs_*.tar.gz')) == proof_archives
    assert not list((tmp_path / 'backups').glob('*.partial.*'))


@pytest.mark.skipif(not BASH, reason="bash is required")
def test_full_local_backup_does_not_silently_skip_missing_uploads(tmp_path, monkeypatch):
    fake_bin = tmp_path / 'bin'
    fake_bin.mkdir()
    executable = fake_bin / 'mysqldump'
    executable.write_text('#!/usr/bin/env bash\nprintf "CREATE TABLE t (id int);\n"\n', encoding='utf-8')
    executable.chmod(0o755)
    monkeypatch.setenv('UPLOAD_BACKUP_SOURCE', str(tmp_path / 'missing-uploads'))
    result = run_backup(tmp_path, ROOT / 'deploy' / 'backup_all.sh')
    assert result.returncode != 0
    assert 'Upload directory missing' in result.stderr
    assert not list((tmp_path / 'backups').glob('uploads_*.tar.gz'))
    assert not list((tmp_path / 'backups').glob('*.partial.*'))


def test_local_backup_failed_publication_removes_partial_file(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("local_backup_safety", ROOT / "deploy" / "win" / "backup_mysql_local.py")
    backup = importlib.util.module_from_spec(spec)
    with patch.dict(os.environ):
        spec.loader.exec_module(backup)

    class Cursor:
        description = [("id",)]

        def execute(self, statement):
            self.statement = statement

        def fetchall(self):
            return [("example",)] if self.statement == "SHOW TABLES" else [(1,)]

        def fetchone(self):
            return ("example", "CREATE TABLE `example` (`id` int)")

    class Connection:
        closed = False

        def cursor(self):
            return Cursor()

        def close(self):
            self.closed = True

    connection = Connection()
    monkeypatch.setattr(backup.pymysql, "connect", lambda **kwargs: connection)
    monkeypatch.setattr(backup, "OUT", tmp_path)
    monkeypatch.setattr(backup, "DB", "backup_test")
    monkeypatch.setattr(backup.os, "replace", lambda *args: (_ for _ in ()).throw(OSError("disk failure")))
    with pytest.raises(OSError, match="disk failure"):
        backup.main()
    assert connection.closed
    assert not list(tmp_path.iterdir())


@pytest.mark.skipif(not BASH, reason="bash is required")
def test_upload_backup_failure_does_not_publish_partial_archive(tmp_path):
    project = tmp_path / "project"
    scripts = project / "deploy"
    scripts.mkdir(parents=True)
    for name in ("backup_mysql.sh", "backup_all.sh"):
        shutil.copy2(ROOT / "deploy" / name, scripts / name)
    uploads = project / "flask_shop" / "flask_shop" / "static" / "upload"
    uploads.mkdir(parents=True)
    (uploads / "image.txt").write_text("test", encoding="utf-8")
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    (fake_bin / "mysqldump").write_text("#!/usr/bin/env bash\nprintf 'test dump'\n", encoding="utf-8")
    (fake_bin / "tar").write_text("#!/usr/bin/env bash\nprintf 'partial' > \"$2\"\nexit 1\n", encoding="utf-8")
    for executable in fake_bin.iterdir():
        executable.chmod(0o755)
    result = run_backup(tmp_path, scripts / "backup_all.sh")
    assert result.returncode != 0
    assert len(list((tmp_path / "backups").glob("*.sql.gz"))) == 1
    assert not list((tmp_path / "backups").glob("uploads_*.tar.gz"))
    assert not list((tmp_path / "backups").glob("*.partial.*"))


@pytest.mark.skipif(not BASH, reason="bash is required")
def test_retention_does_not_delete_another_database_backup(tmp_path):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    executable = fake_bin / "mysqldump"
    executable.write_text("#!/usr/bin/env bash\nprintf 'test dump'\n", encoding="utf-8")
    executable.chmod(0o755)
    directory = tmp_path / "backups"
    directory.mkdir()
    own = directory / "flask_shop_backup_test_20200101_120000.sql.gz"
    other = directory / "flask_shop_backup_test_other_20200101_120000.sql.gz"
    own.write_bytes(b"old")
    other.write_bytes(b"other")
    old_time = time.time() - 10 * 24 * 60 * 60
    os.utime(own, (old_time, old_time))
    os.utime(other, (old_time, old_time))
    result = run_backup(tmp_path, ROOT / "deploy" / "backup_mysql.sh")
    assert result.returncode == 0, result.stderr
    assert not own.exists()
    assert other.read_bytes() == b"other"
