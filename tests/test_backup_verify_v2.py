"""Backup verification must open the database copy with the right key: the raw
Argon2id key on a v2 install, the passphrase on v1. Regression test for the
'file is not a database' failure when verifying a v2 backup with the passphrase.
"""
import zipfile

import pytest
import sqlcipher3

from core import encryption_v2 as v2
from utils import backup

PW = "verify-pw"


@pytest.fixture(autouse=True)
def fast_kdf(monkeypatch):
    real = v2.derive_master
    monkeypatch.setattr(
        v2, "derive_master",
        lambda pw, salt, **kw: real(pw, salt, memory_cost=64, iterations=1, lanes=1))
    v2._key_cache.clear()


class _FakeDB:
    def __init__(self, password):
        self.password = password


def _zip_db(db_path, out):
    with zipfile.ZipFile(out, "w") as zf:
        zf.write(db_path, "data/edgecase.db")
    return out


def test_verify_v2_backup(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    db_path = data / "edgecase.db"
    keyinfo = data / ".keyinfo"

    salt = v2.new_salt()
    db_key_hex, file_key = v2.derive_subkeys(v2.derive_master(PW, salt))
    con = sqlcipher3.connect(str(db_path))
    con.execute(f"PRAGMA key = \"x'{db_key_hex}'\"")
    con.execute("CREATE TABLE t(x)")
    con.execute("INSERT INTO t VALUES (1)")
    con.commit()
    con.close()
    v2.write_keyinfo(salt, v2.make_verification_token(file_key), path=keyinfo)
    monkeypatch.setattr(v2, "KEYINFO_FILE", keyinfo)

    zip_path = _zip_db(db_path, tmp_path / "backup.zip")
    # v2-aware verification must pass (would raise "file is not a database"
    # if it tried the passphrase).
    backup._verify_zipped_database(zip_path, _FakeDB(PW))
    assert zip_path.exists()  # not discarded


def test_verify_v1_backup_still_works(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    db_path = data / "edgecase.db"

    con = sqlcipher3.connect(str(db_path))
    con.execute(f"PRAGMA key = '{PW}'")
    con.execute("CREATE TABLE t(x)")
    con.execute("INSERT INTO t VALUES (1)")
    con.commit()
    con.close()
    # No .keyinfo -> passphrase path.
    monkeypatch.setattr(v2, "KEYINFO_FILE", data / ".keyinfo")

    zip_path = _zip_db(db_path, tmp_path / "backup.zip")
    backup._verify_zipped_database(zip_path, _FakeDB(PW))
    assert zip_path.exists()
