"""Stage 4: crypto v1 -> v2 migration runner — happy path, rollback, recovery.

Each test builds a synthetic v1 install in a temp dir (passphrase-keyed DB +
Fernet files) and exercises core.migrate_crypto against it. The fast_kdf
fixture swaps Argon2id to cheap params so the suite stays quick; the runner and
the assertions derive consistently, so correctness is unaffected.
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
from core import migrate_crypto as mc

PW = "synth-master-pw"


@pytest.fixture(autouse=True)
def fast_kdf(monkeypatch):
    # Cheap KDF now comes from the central two-variable switch in
    # conftest (EDGECASE_FAST_KDF + EDGECASE_DATA); no local patch.
    v2._key_cache.clear()


def _v1_fernet(pw, salt):
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=480000)
    return Fernet(base64.urlsafe_b64encode(kdf.derive(pw.encode())))


def _build_v1_install(root: Path):
    (root / "data").mkdir(parents=True)
    (root / "assets").mkdir()
    salt = os.urandom(32)
    (root / "data" / ".salt").write_bytes(salt)
    (root / "data" / ".secret_key").write_bytes(os.urandom(24))
    fer = _v1_fernet(PW, salt)
    originals = {}
    specs = [
        ("attachments/att1.bin", os.urandom(300)),
        ("attachments/att2.bin", os.urandom(1200)),
        ("attachments/7/42/Statement_1.pdf", b"%PDF" + os.urandom(500)),
        ("assets/logo.png", b"PNG" + os.urandom(200)),
        ("assets/signature.png", b"SIG" + os.urandom(150)),
    ]
    for rel, data in specs:
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(fer.encrypt(data))
        originals[rel] = data
    (root / "assets" / "icon.icns").write_bytes(b"icnsPLAIN" * 20)  # plain; leave alone

    con = sqlite3.connect(str(root / "data" / "edgecase.db"))
    con.execute(f"PRAGMA key = '{PW}'")
    con.execute("CREATE TABLE client_types(id INTEGER PRIMARY KEY, name TEXT)")
    con.executemany("INSERT INTO client_types(name) VALUES(?)", [("A",), ("B",)])
    con.execute("CREATE TABLE entries(id INTEGER PRIMARY KEY, body TEXT)")
    con.executemany("INSERT INTO entries(body) VALUES(?)", [("x",), ("y",), ("z",)])
    con.commit()
    con.close()
    return originals


def _opens_with_passphrase(db_path):
    con = sqlite3.connect(str(db_path))
    try:
        con.execute(f"PRAGMA key = '{PW}'")
        con.execute("SELECT COUNT(*) FROM client_types")
        return True
    except Exception:
        return False
    finally:
        con.close()


def _v2_keys(root):
    salt, _token = v2.read_keyinfo(path=root / "data" / ".keyinfo")
    return v2.derive_subkeys(v2.derive_master(PW, salt))


def _opens_with_raw_key(root):
    db_key_hex, _ = _v2_keys(root)
    con = sqlite3.connect(str(root / "data" / "edgecase.db"))
    try:
        con.execute(f"PRAGMA key = \"x'{db_key_hex}'\"")
        return con.execute("SELECT COUNT(*) FROM client_types").fetchone()[0]
    finally:
        con.close()


def test_needs_migration_detection(tmp_path):
    _build_v1_install(tmp_path)
    assert mc.needs_migration(root=tmp_path) is True
    mc.migrate(PW, root=tmp_path)
    assert mc.needs_migration(root=tmp_path) is False  # now v2


def test_happy_path(tmp_path):
    originals = _build_v1_install(tmp_path)
    result = mc.migrate(PW, root=tmp_path)

    assert result["status"] == "migrated"
    assert result["files_migrated"] == len(originals)  # 5 v1 files
    assert (tmp_path / "data" / ".keyinfo").exists()
    assert not (tmp_path / "data" / ".v2_migrating").exists()
    assert not (tmp_path / "data" / "edgecase.db.v2new").exists()

    # DB now opens with the raw key, not the passphrase, rows preserved.
    assert _opens_with_raw_key(tmp_path) == 2
    assert not _opens_with_passphrase(tmp_path / "data" / "edgecase.db")

    # Every encrypted file is now v2 and decrypts to its original plaintext.
    _db_key, file_key = _v2_keys(tmp_path)
    for rel, data in originals.items():
        blob = (tmp_path / rel).read_bytes()
        assert v2.is_v2(blob)
        assert v2.decrypt_bytes(file_key, blob) == data

    # The plain icon was left untouched.
    assert (tmp_path / "assets" / "icon.icns").read_bytes() == b"icnsPLAIN" * 20


def test_rollback_on_failure(tmp_path, monkeypatch):
    originals = _build_v1_install(tmp_path)

    # Simulate a crash during step 4 (after files were re-encrypted).
    monkeypatch.setattr(mc, "_build_raw_keyed_db",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))

    with pytest.raises(RuntimeError):
        mc.migrate(PW, root=tmp_path)

    # Clean v1 again: no v2 artifacts, marker gone, DB opens with passphrase.
    assert not (tmp_path / "data" / ".keyinfo").exists()
    assert not (tmp_path / "data" / ".v2_migrating").exists()
    assert not (tmp_path / "data" / "edgecase.db.v2new").exists()
    assert _opens_with_passphrase(tmp_path / "data" / "edgecase.db")

    # Files restored to v1 and still decrypt to originals.
    salt = (tmp_path / "data" / ".salt").read_bytes()
    fer = _v1_fernet(PW, salt)
    for rel, data in originals.items():
        blob = (tmp_path / rel).read_bytes()
        assert v2.is_v1(blob)
        assert fer.decrypt(blob) == data


def test_recover_finalizes_completed(tmp_path):
    # A fully-successful migration whose marker write was "interrupted".
    _build_v1_install(tmp_path)
    mc.migrate(PW, root=tmp_path)
    # Re-create the marker + a stray temp DB + a stale sidecar.
    (tmp_path / "data" / ".v2_migrating").write_text(
        json.dumps({"backup_filename": "pre_v2_migration.zip",
                    "backup_dir": str(tmp_path / "backups")}))
    (tmp_path / "data" / "edgecase.db.v2new").write_bytes(b"stale")
    (tmp_path / "data" / "edgecase.db-wal").write_bytes(b"stale")

    assert mc.recover_if_interrupted(root=tmp_path) == "finalized"
    assert not (tmp_path / "data" / ".v2_migrating").exists()
    assert not (tmp_path / "data" / "edgecase.db.v2new").exists()
    assert not (tmp_path / "data" / "edgecase.db-wal").exists()
    assert (tmp_path / "data" / ".keyinfo").exists()
    assert _opens_with_raw_key(tmp_path) == 2  # v2 state preserved


def test_recover_rolls_back_interrupted(tmp_path):
    # Hard crash mid-file-migration: backup taken, marker written, some files
    # already v2, DB still v1, no .keyinfo.
    originals = _build_v1_install(tmp_path)
    paths = mc._resolve_paths(tmp_path)
    backup_info = mc._zip_backup(paths)            # captures clean v1 state
    mc._write_marker(paths, backup_info)

    # Re-encrypt two files to v2 to simulate partial progress.
    salt = (tmp_path / "data" / ".salt").read_bytes()
    _dbk, file_key = v2.derive_subkeys(v2.derive_master(PW, salt))
    for rel in ("attachments/att1.bin", "assets/logo.png"):
        p = tmp_path / rel
        plain = _v1_fernet(PW, salt).decrypt(p.read_bytes())
        p.write_bytes(v2.encrypt_bytes(file_key, plain))

    assert mc.recover_if_interrupted(root=tmp_path) == "rolled_back"

    # Clean v1: no marker/keyinfo, DB opens with passphrase, all files v1 again.
    assert not (tmp_path / "data" / ".v2_migrating").exists()
    assert not (tmp_path / "data" / ".keyinfo").exists()
    assert _opens_with_passphrase(tmp_path / "data" / "edgecase.db")
    fer = _v1_fernet(PW, salt)
    for rel, data in originals.items():
        blob = (tmp_path / rel).read_bytes()
        assert v2.is_v1(blob)
        assert fer.decrypt(blob) == data


# --- Stage 5: v2 master-password change -------------------------------------

NEW_PW = "new-master-pw-2"


def _keys_for(root, password):
    salt, _ = v2.read_keyinfo(path=root / "data" / ".keyinfo")
    return v2.derive_subkeys(v2.derive_master(password, salt))


def _opens_raw(root, db_key_hex):
    con = sqlite3.connect(str(root / "data" / "edgecase.db"))
    try:
        con.execute(f"PRAGMA key = \"x'{db_key_hex}'\"")
        return con.execute("SELECT COUNT(*) FROM client_types").fetchone()[0]
    except Exception:
        return None
    finally:
        con.close()


def test_change_password_happy(tmp_path):
    originals = _build_v1_install(tmp_path)
    mc.migrate(PW, root=tmp_path)
    old_db_key, old_file_key = _keys_for(tmp_path, PW)

    result = mc.change_password(PW, NEW_PW, root=tmp_path)

    assert result["status"] == "rekeyed"
    assert result["files_rekeyed"] == len(originals)
    assert (tmp_path / "data" / ".keyinfo").exists()
    assert not (tmp_path / "data" / ".v2_migrating").exists()
    assert not (tmp_path / "data" / "edgecase.db.v2new").exists()

    new_db_key, new_file_key = _keys_for(tmp_path, NEW_PW)
    assert _opens_raw(tmp_path, new_db_key) == 2          # new password opens
    assert _opens_raw(tmp_path, old_db_key) is None       # old key no longer
    for rel, data in originals.items():
        blob = (tmp_path / rel).read_bytes()
        assert v2.is_v2(blob)
        assert v2.decrypt_bytes(new_file_key, blob) == data
        with pytest.raises(Exception):
            v2.decrypt_bytes(old_file_key, blob)


def test_change_password_rollback(tmp_path, monkeypatch):
    originals = _build_v1_install(tmp_path)
    mc.migrate(PW, root=tmp_path)
    old_salt, _ = v2.read_keyinfo(path=tmp_path / "data" / ".keyinfo")
    old_db_key, old_file_key = v2.derive_subkeys(v2.derive_master(PW, old_salt))

    monkeypatch.setattr(mc, "_build_rekeyed_db_v2",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    with pytest.raises(RuntimeError):
        mc.change_password(PW, NEW_PW, root=tmp_path)

    # Rolled back to the pre-change v2 state: same salt, old key still opens.
    assert not (tmp_path / "data" / ".v2_migrating").exists()
    cur_salt, _ = v2.read_keyinfo(path=tmp_path / "data" / ".keyinfo")
    assert cur_salt == old_salt
    assert _opens_raw(tmp_path, old_db_key) == 2
    for rel, data in originals.items():
        assert v2.decrypt_bytes(old_file_key, (tmp_path / rel).read_bytes()) == data


def test_recover_rekey_finalized(tmp_path):
    _build_v1_install(tmp_path)
    mc.migrate(PW, root=tmp_path)
    mc.change_password(PW, NEW_PW, root=tmp_path)
    cur_salt, _ = v2.read_keyinfo(path=tmp_path / "data" / ".keyinfo")
    new_db_key, _ = v2.derive_subkeys(v2.derive_master(NEW_PW, cur_salt))

    # Stuck marker whose new salt matches the committed .keyinfo -> finalize.
    (tmp_path / "data" / ".v2_migrating").write_text(json.dumps(
        {"kind": "rekey_v2", "new_salt": cur_salt.hex(),
         "backup_filename": "x.zip", "backup_dir": str(tmp_path / "backups")}))
    (tmp_path / "data" / "edgecase.db.v2new").write_bytes(b"stale")

    assert mc.recover_if_interrupted(root=tmp_path) == "finalized"
    assert not (tmp_path / "data" / ".v2_migrating").exists()
    assert not (tmp_path / "data" / "edgecase.db.v2new").exists()
    assert _opens_raw(tmp_path, new_db_key) == 2


def test_recover_rekey_rolled_back(tmp_path):
    originals = _build_v1_install(tmp_path)
    mc.migrate(PW, root=tmp_path)
    salt_A, _ = v2.read_keyinfo(path=tmp_path / "data" / ".keyinfo")
    dbk_A, fk_A = v2.derive_subkeys(v2.derive_master(PW, salt_A))

    paths = mc._resolve_paths(tmp_path)
    backup_info = mc._zip_backup(paths)        # captures state A incl. .keyinfo
    new_salt = v2.new_salt()                   # a never-committed new salt
    _, fk_new = v2.derive_subkeys(v2.derive_master(NEW_PW, new_salt))
    mc._write_marker(paths, backup_info, kind="rekey_v2", new_salt=new_salt)

    # Partially re-encrypt two files to the (uncommitted) new file key.
    for rel in ("attachments/att1.bin", "assets/logo.png"):
        p = tmp_path / rel
        p.write_bytes(v2.encrypt_bytes(fk_new, v2.decrypt_bytes(fk_A, p.read_bytes())))

    # On-disk .keyinfo salt (A) != marker new salt -> roll back to state A.
    assert mc.recover_if_interrupted(root=tmp_path) == "rolled_back"
    assert not (tmp_path / "data" / ".v2_migrating").exists()
    cur_salt, _ = v2.read_keyinfo(path=tmp_path / "data" / ".keyinfo")
    assert cur_salt == salt_A                   # old key-info restored from backup
    assert _opens_raw(tmp_path, dbk_A) == 2
    for rel, data in originals.items():
        assert v2.decrypt_bytes(fk_A, (tmp_path / rel).read_bytes()) == data


# ---------------------------------------------------------------------------
# Fresh installs: "v1" with nothing on disk but the just-created database
# ---------------------------------------------------------------------------

def _build_fresh_install(root: Path):
    """What Database() leaves behind on a brand-new first run: a
    passphrase-keyed DB with schema, and NOTHING else — no .salt (nothing
    was ever Fernet-encrypted), no .secret_key, no attachments."""
    (root / "data").mkdir(parents=True)
    con = sqlite3.connect(str(root / "data" / "edgecase.db"))
    con.execute(f"PRAGMA key = '{PW}'")
    con.execute("CREATE TABLE client_types(id INTEGER PRIMARY KEY, name TEXT)")
    con.execute("INSERT INTO client_types(name) VALUES('A')")
    con.commit()
    con.close()


def test_fresh_install_counts_as_v1_and_needs_v3(tmp_path):
    _build_fresh_install(tmp_path)
    assert mc.install_crypto_version(root=tmp_path) == 1
    assert mc.needs_v3_migration(root=tmp_path) is True


def test_fresh_install_migrates_to_v3_without_salt(tmp_path):
    """The first-run path: no .salt on disk. The v1 branch must tolerate its
    absence instead of crashing on read_bytes — this is what hands a NEW
    user their recovery key on day one instead of day two."""
    _build_fresh_install(tmp_path)
    result = mc.migrate_to_v3(PW, root=tmp_path)

    assert result["status"] == "migrated_to_v3"
    assert result["from_version"] == 1
    assert result["files_migrated"] == 0
    assert result["recovery_key"]
    assert mc.install_crypto_version(root=tmp_path) == 3
    assert (tmp_path / "data" / ".rk_pending").exists()
    assert not (tmp_path / "data" / ".salt").exists()  # none invented

    # Both fresh credentials open the wrapped master, and the master's
    # derived key opens the database.
    from core import encryption_v3 as v3
    blob = (tmp_path / "data" / ".keyinfo").read_bytes()
    master_pw = v3.unwrap_with_password(blob, PW)
    master_rk = v3.unwrap_with_recovery_key(blob, result["recovery_key"])
    assert master_pw == master_rk
    db_key_hex, _ = v2.derive_subkeys(master_pw)
    con = sqlite3.connect(str(tmp_path / "data" / "edgecase.db"))
    try:
        con.execute(f"PRAGMA key = \"x'{db_key_hex}'\"")
        assert con.execute("SELECT COUNT(*) FROM client_types").fetchone()[0] == 1
    finally:
        con.close()
