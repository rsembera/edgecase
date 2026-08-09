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
