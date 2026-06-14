"""Unit tests for the v2 encryption primitives (core/encryption_v2.py).

The Argon2id KDF runs with cheap parameters here so the suite stays fast;
the real production parameters are exercised by the dry-run harness.
"""
import os

import pytest

from core import encryption_v2 as v2

# Cheap KDF params for fast tests (production uses 256 MiB / t=6 / p=1)
CHEAP = dict(memory_cost=64, iterations=1, lanes=1)


def _keys(password="correct horse battery", salt=None):
    salt = salt if salt is not None else v2.new_salt()
    master = v2.derive_master(password, salt, **CHEAP)
    return v2.derive_subkeys(master)


@pytest.mark.parametrize("size", [0, 1, 15, 16, 17, 1024, 100_000])
def test_roundtrip_various_sizes(size):
    _, fk = _keys()
    pt = os.urandom(size)
    assert v2.decrypt_bytes(fk, v2.encrypt_bytes(fk, pt)) == pt


def test_version_byte_and_dispatch():
    _, fk = _keys()
    blob = v2.encrypt_bytes(fk, b"x")
    assert blob[0] == v2.VERSION == 0x02
    assert v2.is_v2(blob) and not v2.is_v1(blob)
    # A Fernet-style v1 token begins with 0x80
    assert v2.is_v1(b"\x80rest") and not v2.is_v2(b"\x80rest")


def test_wrong_key_fails():
    _, fk1 = _keys(password="pw-one")
    _, fk2 = _keys(password="pw-two")
    blob = v2.encrypt_bytes(fk1, b"secret")
    with pytest.raises(Exception):
        v2.decrypt_bytes(fk2, blob)


def test_tamper_detection():
    _, fk = _keys()
    blob = bytearray(v2.encrypt_bytes(fk, b"secret payload"))
    blob[-1] ^= 0x01  # flip a tag bit
    with pytest.raises(Exception):
        v2.decrypt_bytes(fk, bytes(blob))


def test_derivation_deterministic():
    salt = v2.new_salt()
    a = v2.derive_subkeys(v2.derive_master("pw", salt, **CHEAP))
    b = v2.derive_subkeys(v2.derive_master("pw", salt, **CHEAP))
    assert a == b


def test_salt_changes_keys():
    m1 = v2.derive_master("pw", v2.new_salt(), **CHEAP)
    m2 = v2.derive_master("pw", v2.new_salt(), **CHEAP)
    assert m1 != m2


def test_db_and_file_keys_differ():
    db_hex, fk = _keys()
    assert len(bytes.fromhex(db_hex)) == 32  # valid raw key for SQLCipher
    assert bytes.fromhex(db_hex) != fk       # domain separation holds


def test_verification_token():
    _, fk = _keys(password="right")
    _, wrong = _keys(password="wrong")
    token = v2.make_verification_token(fk)
    assert v2.check_verification_token(fk, token)
    assert not v2.check_verification_token(wrong, token)


def test_keyinfo_file_roundtrip(tmp_path):
    salt = v2.new_salt()
    _, fk = _keys(salt=salt)
    token = v2.make_verification_token(fk)
    p = tmp_path / ".keyinfo"
    v2.write_keyinfo(salt, token, path=p)
    rsalt, rtoken = v2.read_keyinfo(path=p)
    assert rsalt == salt and rtoken == token
    assert v2.check_verification_token(fk, rtoken)


def test_keyinfo_bad_magic(tmp_path):
    p = tmp_path / ".keyinfo"
    p.write_bytes(b"XXXX" + os.urandom(16))
    with pytest.raises(ValueError):
        v2.read_keyinfo(path=p)
