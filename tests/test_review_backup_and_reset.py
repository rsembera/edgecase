"""Backup and reset fixes from the 2026-11-11 review."""
import os
import time

import pytest

from utils import backup
from web.app import app as flask_app


@pytest.fixture
def install(tmp_path, monkeypatch):
    for name in ('data', 'backups'):
        (tmp_path / name).mkdir()
    (tmp_path / 'data' / 'edgecase.db').write_bytes(b'db')
    monkeypatch.setattr(backup, 'DATA_ROOT', tmp_path)
    monkeypatch.setattr(backup, 'DATA_DIR', tmp_path / 'data')
    monkeypatch.setattr(backup, 'ATTACHMENTS_DIR', tmp_path / 'attachments')
    monkeypatch.setattr(backup, 'ASSETS_DIR', tmp_path / 'assets')
    monkeypatch.setattr(backup, 'BACKUPS_DIR', tmp_path / 'backups')
    monkeypatch.setattr(backup, 'MANIFEST_FILE', tmp_path / 'backups' / 'manifest.json')
    return tmp_path


# ---- a new backup folder starts its own chain --------------------------------

def test_switching_backup_folder_takes_a_full_backup(install):
    first, second = install / 'local', install / 'cloud'
    assert backup.create_backup(first)['type'] == 'full'

    (install / 'data' / 'edgecase.db').write_bytes(b'db changed')
    assert backup.create_backup(second)['type'] == 'full'
    assert [p.name[:4] for p in second.glob('*.zip')] == ['full']

    (install / 'data' / 'edgecase.db').write_bytes(b'db changed again')
    assert backup.create_backup(second)['type'] == 'incremental'


# ---- a failed automatic backup is remembered ----------------------------------

class _Db:
    def checkpoint(self):
        pass

    def get_setting(self, key, default=None):
        return {'backup_frequency': 'session'}.get(key, default)


def test_failed_automatic_backup_is_recorded_and_cleared_by_a_good_one(
        install, monkeypatch):
    from web.cli import _run_shutdown_backup
    assert backup.create_backup()['type'] == 'full'
    assert backup.get_backup_error() is None

    def unreachable(*args, **kwargs):
        raise ValueError("Backup folder is not reachable")

    monkeypatch.setattr(backup, 'create_backup', unreachable)
    _run_shutdown_backup(_Db(), label="Test")
    assert "Backup folder is not reachable" in backup.get_backup_error()

    monkeypatch.undo()
    monkeypatch.setattr(backup, 'DATA_ROOT', install)
    monkeypatch.setattr(backup, 'DATA_DIR', install / 'data')
    monkeypatch.setattr(backup, 'ATTACHMENTS_DIR', install / 'attachments')
    monkeypatch.setattr(backup, 'ASSETS_DIR', install / 'assets')
    monkeypatch.setattr(backup, 'BACKUPS_DIR', install / 'backups')
    monkeypatch.setattr(backup, 'MANIFEST_FILE', install / 'backups' / 'manifest.json')
    _run_shutdown_backup(_Db(), label="Test")
    assert backup.get_backup_error() is None


def test_home_page_shows_a_pending_backup_failure_once_per_login(
        client, app_db, install):
    backup.record_backup_error("Backup folder is not reachable")

    first = client.get('/').get_data(as_text=True)
    assert 'Automatic Backup Failed' in first
    assert 'Backup folder is not reachable' in first
    assert 'Automatic Backup Failed' not in client.get('/').get_data(as_text=True)


# ---- reset leaves nothing to key the next setup -------------------------------

def test_reset_removes_key_material_and_releases_the_database(
        client, app_db, monkeypatch):
    from core import config, encryption_v2
    data_dir = config.DATA_DIR
    data_dir.mkdir(parents=True, exist_ok=True)
    names = ['.salt', '.secret_key', '.rk_pending', '.rotate_pending']
    for name in names:
        (data_dir / name).write_bytes(b'x')
    monkeypatch.setattr(encryption_v2, 'KEYINFO_FILE', data_dir / '.keyinfo')
    (data_dir / '.keyinfo').write_bytes(b'ECC3-old-key-file')
    monkeypatch.setattr(app_db, 'verify_password', lambda password: True)
    for mod in ('ATTACHMENTS_DIR', 'BACKUPS_DIR', 'ASSETS_DIR'):
        monkeypatch.setattr(config, mod, data_dir.parent / f'reset-{mod.lower()}')

    resp = client.post('/api/reset_database',
                       json={'password': 'pw', 'confirmation': 'RESET'})

    assert resp.get_json()['success'] is True
    left = [n for n in names + ['.keyinfo'] if (data_dir / n).exists()]
    assert left == []
    assert flask_app.config['db'] is None
