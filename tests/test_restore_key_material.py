"""Restore must put key material back, not just the database.

The backup set deliberately includes .salt, .secret_key and .keyinfo
(test_backup_keyinfo asserts this) — but complete_restore historically
replaced only the database, attachments and assets, leaving the CURRENT
key files on disk. Restoring a backup taken before a password change or
crypto migration then produced an old database under new key material,
which cannot be opened. These tests pin the fix: key state is mirrored
from the backup, including deletion of files the backup does not have.
"""
import json

from utils import backup


def _wire_paths(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    staging = tmp_path / ".restore_staging"
    monkeypatch.setattr(backup, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(backup, "DATA_DIR", data)
    monkeypatch.setattr(backup, "ATTACHMENTS_DIR", tmp_path / "attachments")
    monkeypatch.setattr(backup, "ASSETS_DIR", tmp_path / "assets")
    monkeypatch.setattr(backup, "RESTORE_STAGING_DIR", staging)
    return data, staging


def _stage(staging, files):
    """Build a fake prepared-restore staging dir with a valid marker."""
    (staging / "data").mkdir(parents=True)
    for name, content in files.items():
        (staging / "data" / name).write_bytes(content)
    marker = {
        "restore_point_id": "test_full",
        "prepared_at": "2026-08-14T00:00:00",
        "point_info": {"created_at": "2026-08-01T00:00:00"},
    }
    (staging / ".restore_marker").write_text(json.dumps(marker))


def test_restore_replaces_key_material(tmp_path, monkeypatch):
    """The backup's key files must replace the current ones, so the
    restored database opens with the password in effect at backup time."""
    data, staging = _wire_paths(tmp_path, monkeypatch)

    # Current install: key material from AFTER a password change
    (data / "edgecase.db").write_bytes(b"current-db")
    (data / ".salt").write_bytes(b"new-salt")
    (data / ".secret_key").write_bytes(b"new-secret")
    (data / ".keyinfo").write_bytes(b"ECC3-new")

    # Staged backup: database and key material from BEFORE the change
    _stage(staging, {
        "edgecase.db": b"old-db",
        ".salt": b"old-salt",
        ".secret_key": b"old-secret",
        ".keyinfo": b"ECC3-old",
    })

    result = backup.complete_restore()

    assert result is not None
    assert (data / "edgecase.db").read_bytes() == b"old-db"
    assert (data / ".salt").read_bytes() == b"old-salt"
    assert (data / ".secret_key").read_bytes() == b"old-secret"
    assert (data / ".keyinfo").read_bytes() == b"ECC3-old"


def test_restore_removes_key_files_absent_from_backup(tmp_path, monkeypatch):
    """Restoring a pre-migration (v1) backup onto a migrated install must
    DELETE the stale .keyinfo — keyinfo_exists() would otherwise route key
    derivation down the v2/v3 path for a v1 passphrase-keyed database.
    Same for a stale .rk_pending, which describes the replaced keyinfo."""
    data, staging = _wire_paths(tmp_path, monkeypatch)

    (data / "edgecase.db").write_bytes(b"current-db")
    (data / ".salt").write_bytes(b"salt")
    (data / ".secret_key").write_bytes(b"secret")
    (data / ".keyinfo").write_bytes(b"ECC3")
    (data / ".rk_pending").write_bytes(b"")

    # v1-era backup: no .keyinfo, no .rk_pending
    _stage(staging, {
        "edgecase.db": b"v1-db",
        ".salt": b"v1-salt",
        ".secret_key": b"v1-secret",
    })

    backup.complete_restore()

    assert (data / "edgecase.db").read_bytes() == b"v1-db"
    assert (data / ".salt").read_bytes() == b"v1-salt"
    assert not (data / ".keyinfo").exists()
    assert not (data / ".rk_pending").exists()


def test_restore_reinstates_rk_pending(tmp_path, monkeypatch):
    """A backup taken while the recovery-key acknowledgement was still
    outstanding must bring the flag back, so the nag reappears for the
    (restored) keyinfo whose key was never recorded."""
    data, staging = _wire_paths(tmp_path, monkeypatch)

    (data / "edgecase.db").write_bytes(b"current-db")
    (data / ".keyinfo").write_bytes(b"ECC3-acknowledged")

    _stage(staging, {
        "edgecase.db": b"old-db",
        ".keyinfo": b"ECC3-unacknowledged",
        ".rk_pending": b"",
    })

    backup.complete_restore()

    assert (data / ".rk_pending").exists()
    assert (data / ".keyinfo").read_bytes() == b"ECC3-unacknowledged"


def test_rk_pending_in_backup_set(tmp_path, monkeypatch):
    """The acknowledgement flag is part of key state (as migrate_crypto's
    rollback set already treats it) and belongs in the backup."""
    data, _ = _wire_paths(tmp_path, monkeypatch)
    (data / "edgecase.db").write_bytes(b"db")
    (data / ".rk_pending").write_bytes(b"")

    files = backup.get_all_backup_files()
    assert "data/.rk_pending" in files
