"""Master-key rotation (docs/Master_Rotation_Plan.md).

Before rotation, an old key file plus the old password derives the live
master offline — that is the gap. After it, every earlier key file, password
and recovery key opens nothing current, while the live install still opens
with the same password and every attachment still decrypts.

Synthetic v3 installs are built in temp dirs from the test_migrate_v3
builders; nothing here touches a real checkout. The rotation rolls FORWARD:
the crash tests assert that an interrupted run is resumed, not undone, and
that recover_if_interrupted() keeps its hands off a rotate_master marker.
"""
import json
import os
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest
import sqlcipher3 as sqlite3

from core import encryption_v2 as v2
from core import encryption_v3 as v3
from core import master_rotation as rot
from core import migrate_crypto as mc
from tests.test_migrate_v3 import PAYLOADS, PW, build_v2

NEW_PW = "rotated-master-pw"

# Files the walk must cover beyond the plain PAYLOADS: an unexpected
# extension (the readable-named statement PDFs of Attachment_Filename_Fix_Plan)
# and the logo in assets/, which _candidate_files includes deliberately.
EXTRA = {
    "attachments/2/6/Statement_20251102-KL_20260302.pdf": b"%PDF-1.4 statement",
    "attachments/ledger/7/2025-12-KL.pdf": b"%PDF-1.4 receipt",
    "assets/logo.png": b"\x89PNG logo bytes",
}


def _write_manifest(root: Path, created: datetime, filename="full_test.zip"):
    backups = root / "backups"
    backups.mkdir(exist_ok=True)
    with zipfile.ZipFile(backups / filename, "w") as zf:
        zf.writestr("data/placeholder.txt", "x")
    (backups / "manifest.json").write_text(json.dumps({
        "app": "edgecase",
        "current_chain_id": "c1",
        "last_full_hashes": {},
        "backups": [{
            "filename": filename, "type": "full", "chain_id": "c1",
            "created_at": created.isoformat(), "backup_dir": str(backups),
        }],
    }))


def _keyinfo(root: Path) -> bytes:
    return (root / "data" / ".keyinfo").read_bytes()


def _all_files(root: Path):
    rels = [f"attachments/{n}" for n in PAYLOADS] + list(EXTRA)
    return {rel: root / rel for rel in rels}


def _expected(rel: str) -> bytes:
    if rel.startswith("attachments/") and rel[len("attachments/"):] in PAYLOADS:
        return PAYLOADS[rel[len("attachments/"):]]
    return EXTRA[rel]


@pytest.fixture
def install(tmp_path):
    """A v3 install with attachments, a logo, three DB rows, an acknowledged
    recovery key, and a verified backup taken just now."""
    build_v2(tmp_path)
    result = mc.migrate_to_v3(PW, root=tmp_path)
    mc.clear_recovery_key_pending(root=tmp_path)

    blob = v3.read_keyinfo(path=tmp_path / "data" / ".keyinfo")
    master = v3.unwrap_with_password(blob, PW)
    _db, file_key = v2.derive_subkeys(master)
    for rel, payload in EXTRA.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(v2.encrypt_bytes(file_key, payload))
    (tmp_path / "attachments" / ".DS_Store").write_bytes(b"junk")
    (tmp_path / "attachments" / "2" / ".DS_Store").write_bytes(b"junk")

    _write_manifest(tmp_path, datetime.now())
    return {"root": tmp_path, "old_keyinfo": blob, "old_master": master,
            "old_recovery_key": result["recovery_key"]}


def assert_fully_openable(root: Path, password: str, recovery_key: str = None):
    """Key file unwraps, every candidate file decrypts to its original bytes
    under the derived file key, and the database opens under the derived DB
    key with its rows intact."""
    blob = v3.read_keyinfo(path=root / "data" / ".keyinfo")
    master = v3.unwrap_with_password(blob, password)
    if recovery_key is not None:
        assert v3.unwrap_with_recovery_key(blob, recovery_key) == master
    db_key_hex, file_key = v2.derive_subkeys(master)
    for rel, path in _all_files(root).items():
        assert v2.decrypt_bytes(file_key, path.read_bytes()) == _expected(rel), rel
    con = sqlite3.connect(str(root / "data" / "edgecase.db"))
    con.execute(f"PRAGMA key = \"x'{db_key_hex}'\"")
    assert con.execute("SELECT count(*) FROM clients").fetchone()[0] == 3
    assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    con.close()
    return master


def assert_old_material_opens_nothing(root: Path, old_keyinfo: bytes, old_rk: str):
    """Old key file + old password derives a master that decrypts nothing
    current; the old recovery key is refused by the new key file."""
    stale = v3.unwrap_with_password(old_keyinfo, PW)
    stale_db_hex, stale_fk = v2.derive_subkeys(stale)
    for rel, path in _all_files(root).items():
        with pytest.raises(Exception):
            v2.decrypt_bytes(stale_fk, path.read_bytes())
    assert not rot._db_opens_with(root / "data" / "edgecase.db", stale_db_hex)
    with pytest.raises(ValueError):
        v3.unwrap_with_recovery_key(
            v3.read_keyinfo(path=root / "data" / ".keyinfo"), old_rk)


def _no_residue(root: Path):
    assert not (root / "data" / ".master_rotation_state").exists()
    assert not (root / "data" / ".v2_migrating").exists()
    assert not (root / "data" / ".rotate_pending").exists()
    assert not (root / "data" / "edgecase.db.v2new").exists()


# --- The gap, and closing it -------------------------------------------------

def test_before_rotation_the_gap_is_real(install):
    """Old key file + old password derives the LIVE master offline and
    decrypts a live attachment. This is what rotation exists to close."""
    root = install["root"]
    master = v3.unwrap_with_password(install["old_keyinfo"], PW)
    assert master == install["old_master"]
    _db, fk = v2.derive_subkeys(master)
    blob = (root / "attachments" / "note.txt").read_bytes()
    assert v2.decrypt_bytes(fk, blob) == PAYLOADS["note.txt"]


def test_rotation_closes_it(install):
    root = install["root"]
    result = rot.rotate_master(PW, root=root)

    assert result["status"] == "rotated"
    assert result["files_rekeyed"] == len(PAYLOADS) + len(EXTRA)
    assert result["files_total"] == result["files_rekeyed"]

    new_master = assert_fully_openable(root, PW, result["recovery_key"])
    assert new_master != install["old_master"]
    assert_old_material_opens_nothing(root, install["old_keyinfo"],
                                      install["old_recovery_key"])
    _no_residue(root)


def test_new_recovery_key_works_and_is_never_stored(install):
    root = install["root"]
    rk = rot.rotate_master(PW, root=root)["recovery_key"]
    assert v3.parse_recovery_key(rk)
    assert mc.verify_recovery_key(rk, root=root) is True
    needle = rk.replace("-", "").encode()
    for path in root.rglob("*"):
        if path.is_file():
            assert needle not in path.read_bytes(), f"recovery key leaked into {path}"


def test_rotation_sets_recovery_key_pending(install):
    root = install["root"]
    assert not mc.recovery_key_pending(root=root)
    rot.rotate_master(PW, root=root)
    assert mc.recovery_key_pending(root=root)


def test_password_can_change_in_the_same_operation(install):
    root = install["root"]
    result = rot.rotate_master(PW, new_password=NEW_PW, root=root)
    assert_fully_openable(root, NEW_PW, result["recovery_key"])
    with pytest.raises(ValueError):
        v3.unwrap_with_password(_keyinfo(root), PW)


def test_rotation_clears_the_key_cache(install):
    """Same trap as the v3 password change, worse: the password string is
    unchanged while every key below it has moved, so a stale entry would
    keep handing out keys that open NOTHING on disk."""
    root = install["root"]
    v2._key_cache[PW] = ("deadbeef", b"\x00" * 32)
    rot.rotate_master(PW, root=root)
    assert not v2._key_cache


def test_rotation_clears_the_armed_flag(install):
    root = install["root"]
    rot.arm_rotation(root=root)
    assert rot.rotation_pending(root=root)
    rot.rotate_master(PW, root=root)
    assert not rot.rotation_pending(root=root)


# --- Refusals: nothing touched -------------------------------------------------

def test_wrong_password_is_refused_untouched(install):
    root = install["root"]
    with pytest.raises(ValueError):
        rot.rotate_master("not the password", root=root)
    assert _keyinfo(root) == install["old_keyinfo"]
    _no_residue(root)
    assert_fully_openable(root, PW, install["old_recovery_key"])


def test_refused_on_a_non_v3_install(tmp_path):
    build_v2(tmp_path)
    before = _keyinfo(tmp_path)
    with pytest.raises(rot.RotationError, match="v3"):
        rot.rotate_master(PW, root=tmp_path)
    assert _keyinfo(tmp_path) == before


def test_stale_backup_is_refused_when_a_fresh_one_cannot_be_taken(install):
    """The gate wants a verified backup from the last 24 hours. With only a
    stale one on disk it tries to take a fresh full backup; if THAT fails,
    rotation is refused and the key file is untouched."""
    root = install["root"]
    _write_manifest(root, datetime.now() - timedelta(days=3))

    def no_backup():
        raise OSError("backup volume offline")

    with pytest.raises(rot.RotationError, match="backup"):
        rot.rotate_master(PW, root=root, backup_fn=no_backup)
    assert _keyinfo(root) == install["old_keyinfo"]
    _no_residue(root)
    assert_fully_openable(root, PW, install["old_recovery_key"])


def test_stale_backup_triggers_a_fresh_one_reported_as_its_own_phase(install):
    root = install["root"]
    _write_manifest(root, datetime.now() - timedelta(days=3))
    events = []
    taken = {"n": 0}

    def fresh_backup():
        taken["n"] += 1
        return mc._zip_backup(mc._resolve_paths(root))

    result = rot.rotate_master(PW, root=root, backup_fn=fresh_backup,
                               progress_cb=events.append)

    assert taken["n"] == 1
    assert events[0]["status"] == "backing_up"
    assert result["backup"]["filename"] == "pre_v2_migration.zip"
    assert_fully_openable(root, PW, result["recovery_key"])


def test_fresh_backup_is_not_retaken(install):
    root = install["root"]
    events = []

    def unexpected():
        raise AssertionError("backup_fn must not run when the gate passes")

    result = rot.rotate_master(PW, root=root, backup_fn=unexpected,
                               progress_cb=events.append)
    assert "backing_up" not in [e["status"] for e in events]
    assert result["backup"]["filename"] == "full_test.zip"


def test_corrupt_backup_does_not_satisfy_the_gate(install):
    """A zip that fails verification is not a backup, however recent."""
    root = install["root"]
    (root / "backups" / "full_test.zip").write_bytes(b"not a zip")
    taken = {"n": 0}

    def fresh_backup():
        taken["n"] += 1
        return mc._zip_backup(mc._resolve_paths(root))

    rot.rotate_master(PW, root=root, backup_fn=fresh_backup)
    assert taken["n"] == 1


# --- The walk ----------------------------------------------------------------

def test_unexpected_extension_is_rekeyed_not_skipped(install):
    """The assumption a future refactor is most likely to break: filtering
    the walk by extension would strand every readable-named Statement_*.pdf
    under a master that no longer exists."""
    root = install["root"]
    target = root / "attachments/2/6/Statement_20251102-KL_20260302.pdf"
    before = target.read_bytes()

    result = rot.rotate_master(PW, root=root)

    assert target.read_bytes() != before
    master = v3.unwrap_with_password(_keyinfo(root), PW)
    _db, fk = v2.derive_subkeys(master)
    assert v2.decrypt_bytes(fk, target.read_bytes()) == b"%PDF-1.4 statement"
    assert_old_material_opens_nothing(root, install["old_keyinfo"],
                                      install["old_recovery_key"])
    assert result["files_rekeyed"] == len(PAYLOADS) + len(EXTRA)


def test_assets_logo_is_covered(install):
    root = install["root"]
    rot.rotate_master(PW, root=root)
    master = v3.unwrap_with_password(_keyinfo(root), PW)
    _db, fk = v2.derive_subkeys(master)
    assert v2.decrypt_bytes(fk, (root / "assets/logo.png").read_bytes()) == \
        EXTRA["assets/logo.png"]


def test_dotfiles_are_ignored_without_raising(install):
    root = install["root"]
    rot.rotate_master(PW, root=root)
    assert (root / "attachments" / ".DS_Store").read_bytes() == b"junk"
    assert (root / "attachments" / "2" / ".DS_Store").read_bytes() == b"junk"


def test_file_under_neither_key_stops_rotation_before_anything_is_written(install):
    """Preflight is read-only: a file that opens under neither key refuses
    the whole rotation by name, with no state file and no file touched, so
    the user can still cancel."""
    root = install["root"]
    bad = root / "attachments" / "2" / "6" / "mystery.enc"
    bad.write_bytes(v2.encrypt_bytes(os.urandom(32), b"someone else's"))
    snapshot = {p: p.read_bytes() for p in _all_files(root).values()}

    with pytest.raises(rot.RotationCorruptionError) as err:
        rot.rotate_master(PW, root=root)

    assert "mystery.enc" in str(err.value)
    assert err.value.path == str(bad)
    assert _keyinfo(root) == install["old_keyinfo"]
    _no_residue(root)
    for p, data in snapshot.items():
        assert p.read_bytes() == data, p
    assert not mc.recovery_key_pending(root=root)


def test_rekey_helper_try_old_then_new_semantics(tmp_path):
    old, new, other = os.urandom(32), os.urandom(32), os.urandom(32)
    p = tmp_path / "f.enc"

    p.write_bytes(v2.encrypt_bytes(old, b"x"))
    assert rot._rekey_file_rotation(p, old, new) == "rekeyed"
    assert v2.decrypt_bytes(new, p.read_bytes()) == b"x"

    assert rot._rekey_file_rotation(p, old, new) == "skipped"   # already new

    p.write_bytes(v2.encrypt_bytes(other, b"x"))
    with pytest.raises(rot.RotationCorruptionError):
        rot._rekey_file_rotation(p, old, new)

    p.write_bytes(b"plain, not encrypted")
    with pytest.raises(rot.RotationCorruptionError):
        rot._rekey_file_rotation(p, old, new)


# --- Progress ----------------------------------------------------------------

def test_progress_phases_in_order_with_a_real_bar(install):
    root = install["root"]
    events = []
    rot.rotate_master(PW, root=root, progress_cb=events.append)

    statuses = [e["status"] for e in events]
    order = ["counting", "checking", "encrypting", "database", "finalizing", "complete"]
    seen = [s for s in statuses if s in order]
    assert [s for i, s in enumerate(seen) if i == 0 or seen[i - 1] != s] == order
    encrypting = [e for e in events if e["status"] == "encrypting"]
    total = len(PAYLOADS) + len(EXTRA)
    assert [e["current"] for e in encrypting] == list(range(1, total + 1))
    assert all(e["total"] == total for e in encrypting)
    assert "recovery" not in json.dumps(events).lower()


# --- Roll forward: interruption, resume, and the recovery guard -------------

def _crash_at(monkeypatch, name):
    monkeypatch.setattr(rot, name, lambda *a, **k: (_ for _ in ()).throw(
        RuntimeError(f"crash in {name}")))


def _crash_in_mc(monkeypatch, name):
    monkeypatch.setattr(mc, name, lambda *a, **k: (_ for _ in ()).throw(
        RuntimeError(f"crash in {name}")))


def test_interrupted_rotation_resumes(install):
    """Crash inside the commit window: marker and state both exist, the key
    file is unchanged (the old password still opens the OLD master), the
    files are already under the new key. Re-run: converted files are skipped
    rather than stranded, and both files are gone at the end."""
    root = install["root"]
    with pytest.MonkeyPatch.context() as crash:
        _crash_at(crash, "_commit_rotation")
        with pytest.raises(RuntimeError, match="crash"):
            rot.rotate_master(PW, root=root)

    assert (root / "data" / ".v2_migrating").exists()
    assert (root / "data" / ".master_rotation_state").exists()
    assert _keyinfo(root) == install["old_keyinfo"]
    assert rot.rotation_in_progress(root=root)
    assert rot.rotation_pending(root=root)
    assert not rot.disarm_rotation(root=root), "must not be cancellable mid-run"

    result = rot.rotate_master(PW, root=root)

    assert result["status"] == "rotated"
    assert result["resumed"] is True
    assert result["files_rekeyed"] == 0          # nothing left to convert
    assert_fully_openable(root, PW, result["recovery_key"])
    assert_old_material_opens_nothing(root, install["old_keyinfo"],
                                      install["old_recovery_key"])
    _no_residue(root)


def test_interrupted_walk_resumes_with_the_same_master(install):
    """Die halfway through the file walk: some files under the new key, some
    under the old, no marker yet. The re-run must use the SAME new master —
    minting a second one would strand the first batch."""
    root = install["root"]
    real = rot._rekey_file_rotation
    count = {"n": 0}

    def flaky(path, old, new):
        count["n"] += 1
        if count["n"] == 3:
            raise RuntimeError("power loss mid-walk")
        return real(path, old, new)

    with pytest.MonkeyPatch.context() as crash:
        crash.setattr(rot, "_rekey_file_rotation", flaky)
        with pytest.raises(RuntimeError, match="power loss"):
            rot.rotate_master(PW, root=root)

    state = root / "data" / ".master_rotation_state"
    assert state.exists()
    assert not (root / "data" / ".v2_migrating").exists()
    state_before = state.read_bytes()

    result = rot.rotate_master(PW, root=root)

    assert result["resumed"] is True
    # Two converted before the crash; the re-run converts the rest.
    assert result["files_rekeyed"] == len(PAYLOADS) + len(EXTRA) - 2
    assert_fully_openable(root, PW, result["recovery_key"])
    _no_residue(root)
    assert state_before  # (the state that was reused, not re-minted)


def test_crash_after_db_swap_before_key_file_resumes(install):
    """The narrowest window: the rebuilt database is already swapped in but
    .keyinfo was never written. The old password opens a key file whose DB
    key no longer opens the database. The re-run must detect the swapped
    database and finish with just the key file."""
    root = install["root"]
    with pytest.MonkeyPatch.context() as crash:
        crash.setattr(v3, "write_keyinfo", lambda *a, **k: (_ for _ in ()).throw(
            RuntimeError("crash before keyinfo")))
        with pytest.raises(RuntimeError, match="crash before keyinfo"):
            rot.rotate_master(PW, root=root)

    assert _keyinfo(root) == install["old_keyinfo"]
    old_db_hex, _fk = v2.derive_subkeys(install["old_master"])
    assert not rot._db_opens_with(root / "data" / "edgecase.db", old_db_hex)

    result = rot.rotate_master(PW, root=root)

    assert result["status"] == "rotated" and result["resumed"] is True
    assert_fully_openable(root, PW, result["recovery_key"])
    _no_residue(root)


def test_crash_after_key_file_before_cleanup_finalizes(install):
    """Past the commit point, the run died before clearing state and marker.
    The key file already holds the new master; the re-run must NOT rotate
    again — it finishes the cleanup and issues a fresh recovery key, since
    the one the dead run minted never reached the user."""
    root = install["root"]
    with pytest.MonkeyPatch.context() as crash:
        _crash_at(crash, "_clear_state")
        with pytest.raises(RuntimeError, match="crash"):
            rot.rotate_master(PW, root=root)

    assert _keyinfo(root) != install["old_keyinfo"]
    assert (root / "data" / ".v2_migrating").exists()
    assert (root / "data" / ".master_rotation_state").exists()
    files_after_commit = {p: p.read_bytes() for p in _all_files(root).values()}

    result = rot.rotate_master(PW, root=root)

    assert result["status"] == "finalized"
    for p, data in files_after_commit.items():
        assert p.read_bytes() == data, "finalize must not rotate a second time"
    assert_fully_openable(root, PW, result["recovery_key"])
    assert mc.recovery_key_pending(root=root)
    _no_residue(root)


# --- Database rekey is verified before the swap -------------------------------

def test_database_rekey_is_verified_before_the_swap(install):
    """Corrupt the export: the original database must survive untouched,
    still under the old key, and the rotation must be resumable."""
    root = install["root"]
    db = root / "data" / "edgecase.db"
    db_before = db.read_bytes()
    old_db_hex, _ = v2.derive_subkeys(install["old_master"])

    def corrupt_export(paths, src_key_sql, dst_key_hex):
        paths.new_db.write_bytes(b"garbage" * 100)
        raise RuntimeError("rebuilt DB failed integrity_check")

    with pytest.MonkeyPatch.context() as crash:
        crash.setattr(mc, "_export_verify", corrupt_export)
        with pytest.raises(RuntimeError, match="integrity"):
            rot.rotate_master(PW, root=root)

    assert db.read_bytes() == db_before
    assert rot._db_opens_with(db, old_db_hex)
    assert _keyinfo(root) == install["old_keyinfo"]
    assert not (root / "data" / ".v2_migrating").exists()   # never reached commit

    result = rot.rotate_master(PW, root=root)
    assert result["resumed"] is True
    assert_fully_openable(root, PW, result["recovery_key"])


def test_real_export_verify_rejects_a_corrupt_rebuild(install):
    """Not a stub: run the real _export_verify and corrupt the file it
    produced before its own verification pass."""
    root = install["root"]
    paths = mc._resolve_paths(root)
    old_db_hex, _ = v2.derive_subkeys(install["old_master"])
    new_hex = os.urandom(32).hex()

    real_connect = sqlite3.connect
    calls = {"n": 0}

    def tamper(path, *a, **k):
        # The second connect is the verification open of the NEW file.
        if str(path) == str(paths.new_db):
            calls["n"] += 1
            if calls["n"] == 1:
                with open(path, "r+b") as f:
                    f.seek(4096)
                    f.write(os.urandom(512))
        return real_connect(path, *a, **k)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(mc.sqlite3, "connect", tamper)
        with pytest.raises(Exception):
            mc._build_rekeyed_db_v2(paths, old_db_hex, new_hex)

    assert rot._db_opens_with(paths.db, old_db_hex)


# --- Password-free state queries ----------------------------------------------

def test_arm_disarm_and_pending(install):
    root = install["root"]
    assert not rot.rotation_pending(root=root)
    rot.arm_rotation(root=root)
    assert rot.rotation_armed(root=root) and rot.rotation_pending(root=root)
    assert not rot.rotation_in_progress(root=root)
    assert rot.disarm_rotation(root=root) is True
    assert not rot.rotation_pending(root=root)


def test_unreadable_state_file_is_refused_plainly(install):
    root = install["root"]
    (root / "data" / ".master_rotation_state").write_text("not json")
    with pytest.raises(rot.RotationError, match="state"):
        rot.rotate_master(PW, root=root)
    assert _keyinfo(root) == install["old_keyinfo"]
