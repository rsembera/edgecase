"""Stage 3: Database keys SQLCipher with the raw v2 key when .keyinfo exists.

Verifies the v1/v2 gate in core.database. The v1 (passphrase) path is covered
by the rest of the suite; this exercises the v2 raw-key path end to end through
the real Database class, which is where the fiddly `PRAGMA key = "x'...'"`
quoting would break if wrong.
"""
import sqlcipher3

from core import encryption_v2 as v2
from core.database import Database


def test_database_opens_with_raw_v2_key(tmp_path, monkeypatch):
    pw = "v2-keying-test"
    salt = v2.new_salt()
    db_key_hex, file_key = v2.derive_subkeys(v2.derive_master(pw, salt))

    keyinfo = tmp_path / ".keyinfo"
    v2.write_keyinfo(salt, v2.make_verification_token(file_key), path=keyinfo)

    # Point the v2 module at this temp key-info and pre-warm the cache so the
    # Database doesn't re-run the (slow) production Argon2id during init.
    monkeypatch.setattr(v2, "KEYINFO_FILE", keyinfo)
    v2._key_cache.clear()
    v2._key_cache[pw] = (db_key_hex, file_key)

    db_path = tmp_path / "edgecase.db"
    db = Database(str(db_path), password=pw)  # creates schema under the raw v2 key

    # If keying worked, a real query against the created schema succeeds.
    assert db.connect().execute("SELECT COUNT(*) FROM client_types").fetchone()[0] >= 0

    # The on-disk DB really is raw-keyed: the passphrase must NOT open it,
    # but the raw key must.
    bad = sqlcipher3.connect(str(db_path))
    bad.execute(f"PRAGMA key = '{pw}'")
    try:
        bad.execute("SELECT COUNT(*) FROM client_types")
        opened_with_passphrase = True
    except Exception:
        opened_with_passphrase = False
    finally:
        bad.close()
    assert not opened_with_passphrase, "v2 DB should not open with the passphrase"

    assert db.verify_password(pw) is True
    assert db.verify_password("wrong-password") is False

    v2._key_cache.clear()
