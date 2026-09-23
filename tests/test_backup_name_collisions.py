"""Backups made within the same second must never overwrite each other.

Backup names are stamped to the second (full_2026-09-23_153600.zip), and
before the fix every creation path opened its zip with mode 'w'. A second
backup of the same type in the same second took the same name and
silently replaced the first zip while the manifest went on listing both.
An overwritten incremental's changes vanished from the restore chain with
no error. The naive fix (mode 'x') is a trap: each creation path cleans up
a failed write by unlinking backup_path, and FileExistsError is an OSError,
so the cleanup would have deleted the zip it collided with.

These tests pin the clock so every backup lands in the same wall-clock
second, and advance it only when the code under test sleeps — so they are
deterministic and take no real time.
"""

import time
import zipfile
from datetime import datetime as real_datetime

import pytest

from core.database import Database


FROZEN = real_datetime(2026, 9, 23, 15, 36, 0)


@pytest.fixture
def clock(monkeypatch):
    """Freeze utils.backup's clock; time.sleep advances it instead of waiting."""
    import utils.backup as backup_mod
    state = {'now': FROZEN}

    class FrozenDatetime(real_datetime):
        @classmethod
        def now(cls, tz=None):
            return state['now']

    def fake_sleep(seconds):
        from datetime import timedelta
        state['now'] = state['now'] + timedelta(seconds=seconds)

    monkeypatch.setattr(backup_mod, 'datetime', FrozenDatetime)
    monkeypatch.setattr(time, 'sleep', fake_sleep)
    return state


@pytest.fixture
def backup_env(tmp_path, monkeypatch):
    """Point utils.backup's module-level paths at an isolated root."""
    import utils.backup as backup_mod
    root = tmp_path / 'dataroot'
    (root / 'data').mkdir(parents=True)
    (root / 'attachments').mkdir(parents=True)
    monkeypatch.setattr(backup_mod, 'DATA_ROOT', root)
    monkeypatch.setattr(backup_mod, 'DATA_DIR', root / 'data')
    monkeypatch.setattr(backup_mod, 'ATTACHMENTS_DIR', root / 'attachments')
    monkeypatch.setattr(backup_mod, 'ASSETS_DIR', root / 'assets')
    monkeypatch.setattr(backup_mod, 'BACKUPS_DIR', root / 'backups')
    monkeypatch.setattr(backup_mod, 'MANIFEST_FILE', root / 'backups' / 'manifest.json')
    monkeypatch.setattr(backup_mod, 'RESTORE_STAGING_DIR', root / '.restore_staging')
    db = Database(str(root / 'data' / 'edgecase.db'), password='collision-pw')
    yield backup_mod, root, db
    db.close()


def _zips(root):
    return sorted((root / 'backups').glob('*.zip'))


def _assert_manifest_matches_disk(backup_mod, root, expected):
    manifest = backup_mod.load_manifest()
    names = [b['filename'] for b in manifest['backups']]
    assert len(names) == expected
    assert len(set(names)) == expected, f"duplicate names in manifest: {names}"
    on_disk = {p.name for p in _zips(root)}
    assert on_disk == set(names), f"manifest {names} vs disk {sorted(on_disk)}"
    for p in _zips(root):
        assert p.stat().st_size > 0, f"empty zip left behind: {p.name}"
        with zipfile.ZipFile(p) as zf:
            assert zf.testzip() is None
    return manifest


def test_same_second_fulls_and_incrementals_all_survive(backup_env, clock):
    backup_mod, root, db = backup_env
    att = root / 'attachments' / '1'
    att.mkdir()

    full1 = backup_mod.create_full_backup(db=db)
    full2 = backup_mod.create_full_backup(db=db)

    (att / 'a.enc').write_bytes(b'first change')
    incr1 = backup_mod.create_incremental_backup(db=db)
    (att / 'b.enc').write_bytes(b'second change')
    incr2 = backup_mod.create_incremental_backup(db=db)

    assert incr1 and incr1['type'] == 'incremental'
    assert incr2 and incr2['type'] == 'incremental'
    assert len({full1['filename'], full2['filename'],
                incr1['filename'], incr2['filename']}) == 4
    assert full1['chain_id'] != full2['chain_id']

    manifest = _assert_manifest_matches_disk(backup_mod, root, 4)
    assert manifest['current_chain_id'] == full2['chain_id']
    assert incr1['chain_id'] == incr2['chain_id'] == full2['chain_id']

    # Each incremental still carries its own change.
    with zipfile.ZipFile(root / 'backups' / incr1['filename']) as zf:
        assert 'attachments/1/a.enc' in zf.namelist()
    with zipfile.ZipFile(root / 'backups' / incr2['filename']) as zf:
        assert 'attachments/1/b.enc' in zf.namelist()


def test_chain_id_matches_filename_stamp(backup_env, clock):
    """chain_id comes from the reserved name, so the two never disagree."""
    backup_mod, root, db = backup_env
    backup_mod.create_full_backup(db=db)
    full2 = backup_mod.create_full_backup(db=db)
    stamp = full2['filename'][len('full_'):-len('.zip')]
    assert full2['chain_id'] == stamp.replace('-', '')


def test_same_second_pre_restore_backups_both_survive(backup_env, clock):
    backup_mod, root, db = backup_env
    p1 = backup_mod.create_pre_restore_backup(db=db)
    p2 = backup_mod.create_pre_restore_backup(db=db)
    assert p1 != p2
    _assert_manifest_matches_disk(backup_mod, root, 2)


def test_pre_restore_with_nothing_to_back_up_leaves_no_file(backup_env, clock, monkeypatch):
    backup_mod, root, db = backup_env
    monkeypatch.setattr(backup_mod, 'get_all_backup_files', lambda: {})
    assert backup_mod.create_pre_restore_backup(db=db) is None
    assert _zips(root) == []


def test_failed_write_never_deletes_the_backup_it_collided_with(backup_env, clock, monkeypatch):
    """The 'x'-mode trap: cleanup after a failed write must only touch our own file."""
    backup_mod, root, db = backup_env
    first = backup_mod.create_full_backup(db=db)

    def broken_write(self, *args, **kwargs):
        raise OSError(28, 'No space left on device')
    with monkeypatch.context() as m:
        m.setattr(zipfile.ZipFile, 'write', broken_write)
        with pytest.raises(ValueError):
            backup_mod.create_full_backup(db=db)

    assert [p.name for p in _zips(root)] == [first['filename']]
    with zipfile.ZipFile(root / 'backups' / first['filename']) as zf:
        assert zf.testzip() is None and zf.namelist()


def test_non_oserror_failure_leaves_no_empty_reservation(backup_env, clock, monkeypatch):
    backup_mod, root, db = backup_env

    def exploding_write(self, *args, **kwargs):
        raise RuntimeError('unexpected')
    monkeypatch.setattr(zipfile.ZipFile, 'write', exploding_write)

    with pytest.raises(RuntimeError):
        backup_mod.create_full_backup(db=db)
    assert _zips(root) == []
