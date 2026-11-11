"""The logo and signature travel with the practice.

Uploads are stored as <32 hex>.<ext>, but backup, restore, the encryption
upgrade and key rotation each matched only the old fixed names (logo.*,
signature.*) — so every logo and signature uploaded since the rename was
left out of backups and never re-encrypted (2026-11-11 review).
"""
import io
import json

import pytest

from core import config, encryption, encryption_v2
from utils import backup

UUID_NAME = 'dc92358cee6e49cfb0ae68f2f9211781.png'


def test_is_practice_asset():
    assert config.is_practice_asset(UUID_NAME)
    assert config.is_practice_asset('assets/e0683305ccfd4da59e9a0a098ee49231.JPG')
    assert config.is_practice_asset('logo.png')
    assert config.is_practice_asset('signature.gif')
    assert not config.is_practice_asset('icon.icns')
    assert not config.is_practice_asset('.DS_Store')
    assert not config.is_practice_asset('notes.png')
    assert not config.is_practice_asset('dc92358cee6e49cfb0ae68f2f9211781.icns')


@pytest.fixture
def install(tmp_path, monkeypatch):
    for name in ('data', 'assets', 'attachments'):
        (tmp_path / name).mkdir()
    (tmp_path / 'data' / 'edgecase.db').write_bytes(b'db')
    (tmp_path / 'assets' / UUID_NAME).write_bytes(b'logo-bytes')
    (tmp_path / 'assets' / 'icon.icns').write_bytes(b'app icon')
    monkeypatch.setattr(backup, 'DATA_ROOT', tmp_path)
    monkeypatch.setattr(backup, 'DATA_DIR', tmp_path / 'data')
    monkeypatch.setattr(backup, 'ATTACHMENTS_DIR', tmp_path / 'attachments')
    monkeypatch.setattr(backup, 'ASSETS_DIR', tmp_path / 'assets')
    monkeypatch.setattr(backup, 'RESTORE_STAGING_DIR', tmp_path / '.restore_staging')
    return tmp_path


def test_backup_includes_uploaded_logo_but_not_the_app_icon(install):
    files = backup.get_all_backup_files()
    assert f'assets/{UUID_NAME}' in files
    assert 'assets/icon.icns' not in files


def test_restore_puts_the_uploaded_logo_back(install):
    staging = install / '.restore_staging'
    (staging / 'assets').mkdir(parents=True)
    (staging / 'assets' / UUID_NAME).write_bytes(b'restored-logo')
    (staging / '.restore_marker').write_text(json.dumps({
        'restore_point_id': 'x', 'point_info': {'created_at': '2026-11-11T00:00:00'}}))
    (install / 'assets' / UUID_NAME).unlink()

    backup.complete_restore()

    assert (install / 'assets' / UUID_NAME).read_bytes() == b'restored-logo'


def test_encryption_upgrade_and_rotation_walk_the_uploaded_logo(install):
    from core import migrate_crypto
    names = {p.name for p in migrate_crypto._candidate_files(
        migrate_crypto._resolve_paths(install))}
    assert UUID_NAME in names and 'icon.icns' not in names


def test_legacy_fernet_asset_is_upgraded_and_survives_a_password_change(
        tmp_path, monkeypatch):
    monkeypatch.setattr(encryption, 'DATA_DIR', tmp_path)
    encryption._fernet_cache.clear()
    asset = tmp_path / UUID_NAME

    # As uploaded on a v1 install: Fernet under the password itself.
    asset.write_bytes(b'logo-bytes')
    encryption.encrypt_file(str(asset), 'pw-one')
    assert encryption_v2.is_v1(asset.read_bytes())

    # The install has since been migrated; the asset was missed.
    salt = encryption_v2.new_salt()
    _db, file_key = encryption_v2.derive_subkeys(
        encryption_v2.derive_master('pw-one', salt))
    encryption_v2.write_keyinfo(salt, encryption_v2.make_verification_token(file_key))

    assert encryption.upgrade_legacy_file(str(asset), 'pw-one') == 'upgraded'
    assert encryption_v2.is_v2(asset.read_bytes())
    assert encryption.decrypt_file_to_bytes(str(asset), 'pw-one') == b'logo-bytes'
    assert encryption.upgrade_legacy_file(str(asset), 'pw-one') == 'current'


def test_legacy_asset_the_password_no_longer_opens_is_left_alone(
        tmp_path, monkeypatch):
    monkeypatch.setattr(encryption, 'DATA_DIR', tmp_path)
    encryption._fernet_cache.clear()
    asset = tmp_path / UUID_NAME
    asset.write_bytes(b'logo-bytes')
    encryption.encrypt_file(str(asset), 'pw-one')
    before = asset.read_bytes()
    salt = encryption_v2.new_salt()
    _db, file_key = encryption_v2.derive_subkeys(
        encryption_v2.derive_master('pw-two', salt))
    encryption_v2.write_keyinfo(salt, encryption_v2.make_verification_token(file_key))

    assert encryption.upgrade_legacy_file(str(asset), 'pw-two') == 'failed'
    assert asset.read_bytes() == before


def test_new_upload_removes_the_file_it_replaces(client, app_db, tmp_path, monkeypatch):
    import web.blueprints.settings as settings
    monkeypatch.setattr(settings, 'ASSETS_DIR', tmp_path)

    def upload():
        return client.post('/upload_logo', data={
            'logo': (io.BytesIO(b'\x89PNG'), 'logo.png')},
            content_type='multipart/form-data').get_json()['filename']

    first = upload()
    second = upload()
    assert first != second
    assert [p.name for p in tmp_path.iterdir()] == [second]
