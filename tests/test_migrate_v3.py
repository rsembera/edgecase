"""Crypto v1/v2 -> v3 envelope migration: both sources, rollback, recovery.

The migration is a SINGLE PASS from either starting version, so the thing most
worth pinning is that both sources land on an install that is genuinely
openable and whose attachments still decrypt to their original bytes. After
that, the crash cases: every phase is injected with a failure and the install
must come back as a clean, openable copy of what it started as.

Synthetic installs are built in temp dirs — a v1 (passphrase-keyed DB + Fernet
files) and a v2 (raw-keyed DB + AES-GCM files) — so nothing here touches a real
checkout. fast_kdf swaps Argon2id for cheap params; the runner and assertions
derive consistently, so correctness is unaffected.
"""
import base64
import json
import os
from pathlib import Path

import pytest
import sqlcipher3 as sqlite3
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from core import encryption_v2 as v2
from core import encryption_v3 as v3
from core import migrate_crypto as mc

PW = "synth-master-pw"

# Attachment payloads, including bytes that would break a naive text path.
PAYLOADS = {
    "note.txt": b"clinical note body",
    "scan.bin": bytes(range(256)) * 4,
    "empty.dat": b"",
}


@pytest.fixture(autouse=True)
def fast_kdf(monkeypatch):
    real = v2.derive_master
    monkeypatch.setattr(
        v2, "derive_master",
        lambda pw, salt, **kw: real(pw, salt, memory_cost=64, iterations=1, lanes=1),
    )
    v2._key_cache.clear()
    yield
    v2._key_cache.clear()


# --- Synthetic installs ---

def _v1_fernet(pw, salt):
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=480000)
    return Fernet(base64.urlsafe_b64encode(kdf.derive(pw.encode())))


def _make_dirs(root: Path):
    for sub in ("data", "attachments", "assets", "backups"):
        (root / sub).mkdir(parents=True, exist_ok=True)


def _seed_db(path: Path, key_sql: str):
    con = sqlite3.connect(str(path))
    con.execute(key_sql)
    con.execute("CREATE TABLE client_types (id INTEGER PRIMARY KEY, name TEXT)")
    con.execute("INSERT INTO client_types (name) VALUES ('Individual')")
    con.execute("CREATE TABLE clients (id INTEGER PRIMARY KEY, name TEXT)")
    for n in ("Client A", "Client B", "Client C"):
        con.execute("INSERT INTO clients (name) VALUES (?)", (n,))
    con.commit()
    con.close()


def build_v1(root: Path):
    """A pre-migration install: Fernet attachments, passphrase-keyed DB."""
    _make_dirs(root)
    salt = os.urandom(16)
    (root / "data" / ".salt").write_bytes(salt)
    f = _v1_fernet(PW, salt)
    for name, payload in PAYLOADS.items():
        (root / "attachments" / name).write_bytes(f.encrypt(payload))
    esc = PW.replace("'", "''")
    _seed_db(root / "data" / "edgecase.db", f"PRAGMA key = '{esc}'")


def build_v2(root: Path):
    """A migrated-to-v2 install: ECC2 key-info, AES-GCM files, raw-keyed DB."""
    _make_dirs(root)
    (root / "data" / ".salt").write_bytes(os.urandom(16))
    salt = v2.new_salt()
    db_key_hex, file_key = v2.derive_subkeys(v2.derive_master(PW, salt))
    for name, payload in PAYLOADS.items():
        (root / "attachments" / name).write_bytes(v2.encrypt_bytes(file_key, payload))
    _seed_db(root / "data" / "edgecase.db", f"PRAGMA key = \"x'{db_key_hex}'\"")
    v2.write_keyinfo(salt, v2.make_verification_token(file_key),
                     path=root / "data" / ".keyinfo")


BUILDERS = {"v1": build_v1, "v2": build_v2}


@pytest.fixture(params=["v1", "v2"])
def install(request, tmp_path):
    """Both upgrade paths, run through every shared assertion below."""
    BUILDERS[request.param](tmp_path)
    return tmp_path, request.param


# --- Assertions shared by both paths ---

def assert_openable_v3(root: Path, password: str, recovery_key: str = None):
    """The install must be fully openable: key-info unwraps, attachments
    decrypt to their ORIGINAL bytes, and the DB opens under the derived key
    with its rows intact."""
    blob = v3.read_keyinfo(path=root / "data" / ".keyinfo")
    master = v3.unwrap_with_password(blob, password)
    if recovery_key is not None:
        assert v3.unwrap_with_recovery_key(blob, recovery_key) == master, \
            "recovery key does not open the install it was issued for"

    db_key_hex, file_key = v2.derive_subkeys(master)
    for name, payload in PAYLOADS.items():
        blob_on_disk = (root / "attachments" / name).read_bytes()
        assert v2.decrypt_bytes(file_key, blob_on_disk) == payload, name

    con = sqlite3.connect(str(root / "data" / "edgecase.db"))
    con.execute(f"PRAGMA key = \"x'{db_key_hex}'\"")
    assert con.execute("SELECT count(*) FROM clients").fetchone()[0] == 3
    assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    con.close()


def assert_openable_original(root: Path, version: str):
    """After a rollback the install must be a clean, openable copy of what it
    started as — not merely 'not v3'."""
    assert mc.install_crypto_version(root=root) == (1 if version == "v1" else 2)
    if version == "v1":
        f = _v1_fernet(PW, (root / "data" / ".salt").read_bytes())
        for name, payload in PAYLOADS.items():
            assert f.decrypt((root / "attachments" / name).read_bytes()) == payload
        esc = PW.replace("'", "''")
        key_sql = f"PRAGMA key = '{esc}'"
    else:
        salt, token = v2.read_keyinfo(path=root / "data" / ".keyinfo")
        db_key_hex, file_key = v2.derive_subkeys(v2.derive_master(PW, salt))
        assert v2.check_verification_token(file_key, token)
        for name, payload in PAYLOADS.items():
            assert v2.decrypt_bytes(file_key, (root / "attachments" / name)
                                    .read_bytes()) == payload
        key_sql = f"PRAGMA key = \"x'{db_key_hex}'\""

    con = sqlite3.connect(str(root / "data" / "edgecase.db"))
    con.execute(key_sql)
    assert con.execute("SELECT count(*) FROM clients").fetchone()[0] == 3
    con.close()
    assert not (root / "data" / ".rk_pending").exists()
    assert not (root / "data" / ".v2_migrating").exists()


# --- Detection ---

def test_version_detection(install):
    root, version = install
    assert mc.install_crypto_version(root=root) == (1 if version == "v1" else 2)
    assert mc.needs_v3_migration(root=root)


def test_no_migration_needed_once_v3(install):
    root, _v = install
    mc.migrate_to_v3(PW, root=root)
    assert mc.install_crypto_version(root=root) == 3
    assert not mc.needs_v3_migration(root=root)


def test_pending_marker_suppresses_migration(install):
    """An interrupted run belongs to recover_if_interrupted, which needs no
    password — needs_v3_migration must not claim it."""
    root, _v = install
    (root / "data" / ".v2_migrating").write_text("{}")
    assert not mc.needs_v3_migration(root=root)


# --- Happy path, both sources ---

def test_migrates_to_openable_v3(install):
    root, version = install
    result = mc.migrate_to_v3(PW, root=root)

    assert result["status"] == "migrated_to_v3"
    assert result["from_version"] == (1 if version == "v1" else 2)
    assert result["files_migrated"] == len(PAYLOADS)
    assert_openable_v3(root, PW, result["recovery_key"])


def test_recovery_key_returned_and_never_stored(install):
    """The key exists in plaintext exactly once, as the return value."""
    root, _v = install
    rk = mc.migrate_to_v3(PW, root=root)["recovery_key"]
    assert v3.parse_recovery_key(rk)

    needle = rk.replace("-", "").encode()
    for path in root.rglob("*"):
        if path.is_file():
            assert needle not in path.read_bytes(), f"recovery key leaked into {path}"


def test_rk_pending_set_by_migration(install):
    root, _v = install
    mc.migrate_to_v3(PW, root=root)
    assert mc.recovery_key_pending(root=root)
    mc.clear_recovery_key_pending(root=root)
    assert not mc.recovery_key_pending(root=root)


def test_second_run_is_a_noop(install):
    root, _v = install
    first = mc.migrate_to_v3(PW, root=root)
    again = mc.migrate_to_v3(PW, root=root)
    assert again["status"] == "already_v3"
    assert again["recovery_key"] is None
    assert_openable_v3(root, PW, first["recovery_key"])


def test_wrong_password_refused_before_anything_is_touched(install):
    root, version = install
    with pytest.raises(ValueError):
        mc.migrate_to_v3("not the password", root=root)
    assert_openable_original(root, version)


# --- Crash injection: every phase must roll back to a clean original ---

@pytest.mark.parametrize("phase", ["_reencrypt_file", "_reencrypt_file_v2",
                                   "_export_verify", "_commit_v3"])
def test_failure_at_any_phase_rolls_back(install, monkeypatch, phase):
    """Whichever source, whichever phase: the install must come back openable
    as its ORIGINAL version, with attachments byte-identical."""
    root, version = install
    monkeypatch.setattr(mc, phase, lambda *a, **k: (_ for _ in ()).throw(
        RuntimeError("injected failure")))

    try:
        mc.migrate_to_v3(PW, root=root)
    except RuntimeError:
        pass  # phases not on this source's path simply never fire

    if mc.install_crypto_version(root=root) == 3:
        return  # phase belonged to the other source path; nothing to assert
    assert_openable_original(root, version)


def test_rollback_leaves_no_v3_artifacts(install, monkeypatch):
    root, version = install
    monkeypatch.setattr(mc, "_export_verify", lambda *a, **k: (_ for _ in ()).throw(
        RuntimeError("boom")))
    with pytest.raises(RuntimeError):
        mc.migrate_to_v3(PW, root=root)

    assert_openable_original(root, version)
    assert not (root / "data" / "edgecase.db.v2new").exists()
    if version == "v1":
        assert not (root / "data" / ".keyinfo").exists()
    else:
        assert v3.keyinfo_version(path=root / "data" / ".keyinfo") == 2


# --- Hard crash: recover_if_interrupted, password-free ---

def test_hard_crash_before_commit_rolls_back(install):
    """No rollback ran (process died). Next startup must restore the backup.

    Simulated by making the rollback itself die: the marker unlink in the
    except block never runs, leaving exactly the on-disk state a power loss
    would — marker present, DB swap never performed, nothing cleaned up.

    The injection is scoped to its own context so that leaving it restores the
    real functions WITHOUT also reverting the fast_kdf fixture — recovery has
    to run against real code, but the cheap Argon2 params must still match the
    key-info the install was built with.
    """
    root, version = install
    with pytest.MonkeyPatch.context() as crash:
        crash.setattr(mc, "_commit_v3", lambda *a, **k: (_ for _ in ()).throw(
            RuntimeError("power loss")))
        crash.setattr(mc, "_rollback", lambda *a, **k: (_ for _ in ()).throw(
            RuntimeError("died mid-rollback")))
        with pytest.raises(RuntimeError):
            mc.migrate_to_v3(PW, root=root)

    assert (root / "data" / ".v2_migrating").exists(), "marker should survive"
    assert mc.recover_if_interrupted(root=root) == "rolled_back"
    assert_openable_original(root, version)


def test_hard_crash_after_commit_finalizes(install):
    """The ECC3 magic alone proves commit — no salt bookkeeping needed."""
    root, _v = install
    result = mc.migrate_to_v3(PW, root=root)
    # Replay the marker as if the process died just after the key-info landed.
    (root / "data" / ".v2_migrating").write_text(json.dumps(
        {"kind": "migrate_v3", "backup_filename": "irrelevant.zip",
         "backup_dir": str(root / "backups")}))

    assert mc.recover_if_interrupted(root=root) == "finalized"
    assert_openable_v3(root, PW, result["recovery_key"])


def test_finalize_preserves_the_pending_flag(install):
    """A crash between commit and the user writing the key down is exactly
    what .rk_pending is for — finalizing must not clear it."""
    root, _v = install
    mc.migrate_to_v3(PW, root=root)
    (root / "data" / ".v2_migrating").write_text(json.dumps(
        {"kind": "migrate_v3", "backup_filename": "x.zip",
         "backup_dir": str(root / "backups")}))

    assert mc.recover_if_interrupted(root=root) == "finalized"
    assert mc.recovery_key_pending(root=root)


def test_recover_is_a_noop_without_a_marker(install):
    root, _v = install
    assert mc.recover_if_interrupted(root=root) == "none"


# --- v3 password change: rewrap only ---

NEW_PW = "synth-rotated-pw"


@pytest.fixture
def v3_install(install):
    """A migrated v3 install plus the recovery key it was issued."""
    root, version = install
    rk = mc.migrate_to_v3(PW, root=root)["recovery_key"]
    mc.clear_recovery_key_pending(root=root)
    return root, version, rk


def _keyinfo_bytes(root):
    return (root / "data" / ".keyinfo").read_bytes()


def test_password_change_is_a_rewrap_not_a_walk(v3_install):
    """The payoff: attachments and the database are untouched by construction,
    because the master — and so every key below it — does not move."""
    root, _v, rk = v3_install
    master_before = v3.unwrap_with_password(v3.read_keyinfo(
        path=root / "data" / ".keyinfo"), PW)
    db_before = (root / "data" / "edgecase.db").read_bytes()
    files_before = {n: (root / "attachments" / n).read_bytes() for n in PAYLOADS}

    result = mc.change_password(PW, NEW_PW, root=root)

    assert result["status"] == "rewrapped"
    assert result["files_rekeyed"] == 0
    assert (root / "data" / "edgecase.db").read_bytes() == db_before
    for n in PAYLOADS:
        assert (root / "attachments" / n).read_bytes() == files_before[n]
    assert v3.unwrap_with_password(v3.read_keyinfo(
        path=root / "data" / ".keyinfo"), NEW_PW) == master_before


def test_password_change_leaves_install_openable(v3_install):
    root, _v, rk = v3_install
    mc.change_password(PW, NEW_PW, root=root)
    assert_openable_v3(root, NEW_PW, rk)


def test_password_change_revokes_the_old_password(v3_install):
    root, _v, _rk = v3_install
    mc.change_password(PW, NEW_PW, root=root)
    with pytest.raises(ValueError):
        v3.unwrap_with_password(v3.read_keyinfo(
            path=root / "data" / ".keyinfo"), PW)


def test_password_change_clears_the_key_cache(v3_install):
    """The trap this whole path has to avoid.

    Under v3 the derived keys are IDENTICAL either side of a password change,
    so an entry left in _key_cache under the old password string would keep
    handing out working keys for the rest of the process lifetime — a revoked
    password that still opens the install until restart.
    """
    root, _v, _rk = v3_install
    v2._key_cache[PW] = ("deadbeef", b"\x00" * 32)

    mc.change_password(PW, NEW_PW, root=root)

    assert PW not in v2._key_cache, "revoked password still cached"
    assert not v2._key_cache


def test_password_change_does_no_backup_and_leaves_no_marker(v3_install):
    """No file walk means no backup gate and no rollback window to guard."""
    root, _v, _rk = v3_install
    before = set(p.name for p in (root / "backups").iterdir())

    mc.change_password(PW, NEW_PW, root=root)

    assert set(p.name for p in (root / "backups").iterdir()) == before
    assert not (root / "data" / ".v2_migrating").exists()


def test_password_change_refuses_wrong_current_password(v3_install):
    root, _v, rk = v3_install
    blob_before = _keyinfo_bytes(root)

    with pytest.raises(ValueError):
        mc.change_password("not the password", NEW_PW, root=root)

    assert _keyinfo_bytes(root) == blob_before
    assert_openable_v3(root, PW, rk)


# --- Recovery key rotation ---

def test_regenerate_revokes_the_old_recovery_key(v3_install):
    root, _v, old_rk = v3_install

    new_rk = mc.regenerate_recovery_key(PW, root=root)

    assert new_rk != old_rk
    assert_openable_v3(root, PW, new_rk)
    with pytest.raises(ValueError):
        v3.unwrap_with_recovery_key(v3.read_keyinfo(
            path=root / "data" / ".keyinfo"), old_rk)


def test_regenerate_leaves_the_password_working(v3_install):
    root, _v, _rk = v3_install
    mc.regenerate_recovery_key(PW, root=root)
    assert v3.unwrap_with_password(v3.read_keyinfo(
        path=root / "data" / ".keyinfo"), PW)


def test_regenerate_sets_pending_again(v3_install):
    """A newly issued key is also unrecorded until the user types it back."""
    root, _v, _rk = v3_install
    assert not mc.recovery_key_pending(root=root)
    mc.regenerate_recovery_key(PW, root=root)
    assert mc.recovery_key_pending(root=root)


def test_regenerate_refuses_wrong_password(v3_install):
    root, _v, rk = v3_install
    blob_before = _keyinfo_bytes(root)
    with pytest.raises(ValueError):
        mc.regenerate_recovery_key("not the password", root=root)
    assert _keyinfo_bytes(root) == blob_before
    assert_openable_v3(root, PW, rk)


def test_regenerate_refused_on_a_non_v3_install(install):
    root, _version = install
    with pytest.raises(RuntimeError):
        mc.regenerate_recovery_key(PW, root=root)


def test_rotations_are_independent(v3_install):
    """Rotate both credentials; each must revoke only its own half."""
    root, _v, old_rk = v3_install

    mc.change_password(PW, NEW_PW, root=root)
    new_rk = mc.regenerate_recovery_key(NEW_PW, root=root)

    assert_openable_v3(root, NEW_PW, new_rk)
    blob = v3.read_keyinfo(path=root / "data" / ".keyinfo")
    with pytest.raises(ValueError):
        v3.unwrap_with_password(blob, PW)
    with pytest.raises(ValueError):
        v3.unwrap_with_recovery_key(blob, old_rk)


def test_change_password_still_refuses_a_v1_install(tmp_path):
    """The v2 path's precondition must survive the version dispatch."""
    build_v1(tmp_path)
    with pytest.raises(RuntimeError):
        mc.change_password(PW, NEW_PW, root=tmp_path)


# --- The recovery door: core reset ---

def test_recovery_key_opens_and_resets_the_password(v3_install):
    """The door itself: the key gets you in, and you leave with a working
    password and untouched records."""
    root, _v, rk = v3_install
    db_before = (root / "data" / "edgecase.db").read_bytes()

    mc.reset_password_with_recovery_key(rk, NEW_PW, root=root)

    assert_openable_v3(root, NEW_PW, rk)
    assert (root / "data" / "edgecase.db").read_bytes() == db_before


def test_reset_revokes_the_forgotten_password(v3_install):
    root, _v, rk = v3_install
    mc.reset_password_with_recovery_key(rk, NEW_PW, root=root)
    with pytest.raises(ValueError):
        v3.unwrap_with_password(v3.read_keyinfo(
            path=root / "data" / ".keyinfo"), PW)


def test_reset_leaves_the_recovery_key_working(v3_install):
    """Deliberate asymmetry with the password. If a key has leaked, an
    attacker who used it must NOT be able to rotate it and lock the real owner
    out — the owner's written copy has to keep working so they can recover and
    then rotate it themselves."""
    root, _v, rk = v3_install
    mc.reset_password_with_recovery_key(rk, NEW_PW, root=root)
    assert v3.unwrap_with_recovery_key(v3.read_keyinfo(
        path=root / "data" / ".keyinfo"), rk)


def test_reset_clears_the_key_cache(v3_install):
    """Same trap as the password change: identical derived keys either side."""
    root, _v, rk = v3_install
    v2._key_cache[PW] = ("deadbeef", b"\x00" * 32)
    mc.reset_password_with_recovery_key(rk, NEW_PW, root=root)
    assert PW not in v2._key_cache


def test_reset_refuses_a_wrong_recovery_key(v3_install):
    root, _v, rk = v3_install
    blob_before = _keyinfo_bytes(root)
    with pytest.raises(ValueError):
        mc.reset_password_with_recovery_key(
            v3.generate_recovery_key(), NEW_PW, root=root)
    assert _keyinfo_bytes(root) == blob_before
    assert_openable_v3(root, PW, rk)


def test_reset_refuses_a_malformed_recovery_key(v3_install):
    """RecoveryKeyError, not ValueError — 'you mistyped it' has to stay
    distinguishable from 'that is the wrong key'."""
    root, _v, _rk = v3_install
    with pytest.raises(v3.RecoveryKeyError):
        mc.reset_password_with_recovery_key("not-a-key", NEW_PW, root=root)


def test_reset_refused_on_a_non_v3_install(install):
    root, _version = install
    with pytest.raises(RuntimeError):
        mc.reset_password_with_recovery_key(
            v3.generate_recovery_key(), NEW_PW, root=root)


def test_has_recovery_key_tracks_the_install(install):
    """The login page must not advertise a door that does not exist."""
    root, _version = install
    assert not mc.has_recovery_key(root=root)
    mc.migrate_to_v3(PW, root=root)
    assert mc.has_recovery_key(root=root)


def test_reset_then_rotate_retires_the_used_key(v3_install):
    """The full 'my key may have leaked' path: recover, then rotate."""
    root, _v, old_rk = v3_install

    mc.reset_password_with_recovery_key(old_rk, NEW_PW, root=root)
    fresh_rk = mc.regenerate_recovery_key(NEW_PW, root=root)

    assert_openable_v3(root, NEW_PW, fresh_rk)
    with pytest.raises(ValueError):
        v3.unwrap_with_recovery_key(v3.read_keyinfo(
            path=root / "data" / ".keyinfo"), old_rk)


# --- Verification must change nothing ---

def test_verify_accepts_the_right_key(v3_install):
    root, _v, rk = v3_install
    assert mc.verify_recovery_key(rk, root=root) is True


def test_verify_rejects_a_wrong_key(v3_install):
    root, _v, _rk = v3_install
    assert mc.verify_recovery_key(v3.generate_recovery_key(), root=root) is False


def test_verify_changes_absolutely_nothing(v3_install):
    """The entire point. Checking a key must not cost the user their password,
    their key, or anything else — otherwise the prudent person is punished for
    checking and everyone learns not to."""
    root, _v, rk = v3_install
    keyinfo_before = _keyinfo_bytes(root)
    db_before = (root / "data" / "edgecase.db").read_bytes()
    files_before = {n: (root / "attachments" / n).read_bytes() for n in PAYLOADS}
    pending_before = mc.recovery_key_pending(root=root)

    mc.verify_recovery_key(rk, root=root)
    mc.verify_recovery_key(v3.generate_recovery_key(), root=root)  # and a wrong one

    assert _keyinfo_bytes(root) == keyinfo_before
    assert (root / "data" / "edgecase.db").read_bytes() == db_before
    for n in PAYLOADS:
        assert (root / "attachments" / n).read_bytes() == files_before[n]
    assert mc.recovery_key_pending(root=root) == pending_before
    assert_openable_v3(root, PW, rk)


def test_verify_leaves_the_password_working(v3_install):
    """Contrast with reset_password_with_recovery_key, which always revokes."""
    root, _v, rk = v3_install
    mc.verify_recovery_key(rk, root=root)
    assert v3.unwrap_with_password(v3.read_keyinfo(
        path=root / "data" / ".keyinfo"), PW)


def test_verify_distinguishes_mistyped_from_wrong(v3_install):
    """Malformed raises; well-formed-but-wrong returns False. Someone checking
    a key needs to know which of the two happened."""
    root, _v, _rk = v3_install
    with pytest.raises(v3.RecoveryKeyError):
        mc.verify_recovery_key("not-a-key", root=root)
    assert mc.verify_recovery_key(v3.generate_recovery_key(), root=root) is False


def test_verify_refused_on_a_non_v3_install(install):
    root, _version = install
    with pytest.raises(RuntimeError):
        mc.verify_recovery_key(v3.generate_recovery_key(), root=root)
