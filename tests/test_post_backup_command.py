"""A post-backup command that fails must say so, and be tried again.

Bug (Nov 2026, production): the server was stopped with Ctrl+C while the
post-backup rsync to the home server was still running. rsync reported
"error ... (code 255)" and the very next line read "[Logout] Post-backup
command completed": the command's exit status was never looked at. A copy
that really had failed would have passed unnoticed, and the desktop app has
no console to read at all.

Now a failure is reported as a failure, kept for the next login like a
failed automatic backup, and the command is run again at the next session
end even if there is nothing new to back up — the off-site copy is still
owed.
"""
import sys

import pytest

from utils import backup
from web.app import app as flask_app  # noqa: F401  (configures the app)

PY = sys.executable


@pytest.fixture
def install(tmp_path, monkeypatch):
    root = tmp_path
    for name in ('data', 'backups'):
        (root / name).mkdir()
    (root / 'data' / 'edgecase.db').write_bytes(b'db')
    monkeypatch.setattr(backup, 'DATA_ROOT', root)
    monkeypatch.setattr(backup, 'DATA_DIR', root / 'data')
    monkeypatch.setattr(backup, 'ATTACHMENTS_DIR', root / 'attachments')
    monkeypatch.setattr(backup, 'ASSETS_DIR', root / 'assets')
    monkeypatch.setattr(backup, 'BACKUPS_DIR', root / 'backups')
    monkeypatch.setattr(backup, 'MANIFEST_FILE', root / 'backups' / 'manifest.json')
    return root


class _Db:
    def __init__(self, command):
        self.command = command

    def checkpoint(self):
        pass

    def get_setting(self, key, default=None):
        return {'backup_frequency': 'session',
                'post_backup_command': self.command}.get(key, default)


NEW_BACKUP = {'filename': 'incr_2026-11-28_143700.zip', 'type': 'incremental'}


def _backup_makes(monkeypatch, result):
    """Stand in for create_backup (it needs a real encrypted database):
    `result` is what it reports, None meaning nothing had changed."""
    monkeypatch.setattr(backup, 'create_backup', lambda *a, **k: result)


def _exit(code):
    return f'{PY} -c "import sys; sys.exit({code})"'


def _touch(path):
    return f'{PY} -c "open(r\'{path}\', \'a\').close()"'


# -- the command runner ------------------------------------------------------

def test_success_reports_nothing():
    assert backup.run_post_backup_command(_exit(0)) is None


def test_nonzero_exit_is_a_failure():
    assert backup.run_post_backup_command(_exit(255)) == "exit code 255"


def test_a_command_that_cannot_start_is_a_failure():
    assert "could not be run" in backup.run_post_backup_command("/no/such/program --x")


def test_a_command_that_overruns_is_a_failure():
    slow = f'{PY} -c "import time; time.sleep(5)"'
    assert "did not finish" in backup.run_post_backup_command(slow, timeout=0.3)


# -- the end-of-session backup ----------------------------------------------

def test_failed_command_is_not_reported_as_completed(install, capsys, monkeypatch):
    from web.cli import _run_shutdown_backup
    _backup_makes(monkeypatch, NEW_BACKUP)
    _run_shutdown_backup(_Db(_exit(255)), label="Logout")
    out = capsys.readouterr().out
    assert "Backup completed" in out
    assert "Post-backup command completed" not in out
    assert "Post-backup command FAILED (exit code 255)" in out
    warning = backup.get_backup_error()
    assert "post-backup command failed (exit code 255)" in warning
    assert "backup was made" in warning


def test_successful_command_still_reports_completed(install, capsys, monkeypatch):
    from web.cli import _run_shutdown_backup
    _backup_makes(monkeypatch, NEW_BACKUP)
    _run_shutdown_backup(_Db(_exit(0)), label="Logout")
    assert "Post-backup command completed" in capsys.readouterr().out
    assert backup.get_backup_error() is None


def test_failed_command_is_retried_when_nothing_new_to_back_up(install, capsys, monkeypatch):
    from web.cli import _run_shutdown_backup
    _backup_makes(monkeypatch, NEW_BACKUP)
    _run_shutdown_backup(_Db(_exit(1)), label="Logout")
    assert backup.get_backup_error()

    _backup_makes(monkeypatch, None)
    marker = install / 'ran'
    _run_shutdown_backup(_Db(_touch(marker)), label="Logout")
    out = capsys.readouterr().out
    assert "No changes since last backup" in out
    assert marker.exists(), "the copy that failed last time was not tried again"
    assert backup.get_backup_error() is None


def test_command_is_not_run_when_nothing_changed_and_nothing_is_owed(install, monkeypatch):
    from web.cli import _run_shutdown_backup
    _backup_makes(monkeypatch, NEW_BACKUP)
    _run_shutdown_backup(_Db(_exit(0)), label="Logout")
    _backup_makes(monkeypatch, None)
    marker = install / 'ran'
    _run_shutdown_backup(_Db(_touch(marker)), label="Logout")
    assert not marker.exists()


def test_retry_that_fails_again_stays_recorded(install, monkeypatch):
    from web.cli import _run_shutdown_backup
    _backup_makes(monkeypatch, NEW_BACKUP)
    _run_shutdown_backup(_Db(_exit(1)), label="Logout")
    _backup_makes(monkeypatch, None)
    _run_shutdown_backup(_Db(_exit(1)), label="Logout")
    assert "post-backup command failed" in backup.get_backup_error()


def test_removing_the_command_drops_the_owed_retry(install, monkeypatch):
    from web.cli import _run_shutdown_backup
    _backup_makes(monkeypatch, NEW_BACKUP)
    _run_shutdown_backup(_Db(_exit(1)), label="Logout")
    _backup_makes(monkeypatch, None)
    _run_shutdown_backup(_Db(''), label="Logout")
    assert backup.get_backup_error() is None


# -- Back Up Now -------------------------------------------------------------

def test_backup_now_reports_a_failed_command(client, app_db, install, monkeypatch):
    _backup_makes(monkeypatch, NEW_BACKUP)
    app_db.set_setting('post_backup_command', _exit(3))
    data = client.post('/api/backup/now').get_json()
    assert data['success'] is True and data['backup']
    assert "exit code 3" in data['warning']
    assert "post-backup command failed (exit code 3)" in backup.get_backup_error()


def test_backup_now_has_no_warning_when_the_command_succeeds(client, app_db, install, monkeypatch):
    _backup_makes(monkeypatch, NEW_BACKUP)
    app_db.set_setting('post_backup_command', _exit(0))
    data = client.post('/api/backup/now').get_json()
    assert data['success'] is True and not data.get('warning')
    assert backup.get_backup_error() is None
