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
    real = v2.derive_master
    monkeypatch.setattr(
        v2, "derive_master",
        lambda pw, salt, **kw: real(pw, salt, memory_cost=64, iterations=1, lanes=1),
    )
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
