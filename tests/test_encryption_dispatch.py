"""core.encryption must be version-aware after migration: read v1 (Fernet) and
v2 (Argon2id/AES-GCM) files, and write v2 on a migrated install. Without this,
attachments/logo/signature/statements are unreadable once migrated.
"""
import pytest

from core import encryption as enc
from core import encryption_v2 as v2

PW = "file-pw"


@pytest.fixture(autouse=True)
def setup(monkeypatch):
    # Cheap KDF now comes from the central two-variable switch in
    # conftest (EDGECASE_FAST_KDF + EDGECASE_DATA); no local patch.
    v2._key_cache.clear()
    monkeypatch.setattr(enc, "_get_salt", lambda: b"0123456789abcdef")  # stable v1 salt
    enc._fernet_cache.clear()


def _make_v1(monkeypatch, tmp_path):
    monkeypatch.setattr(v2, "KEYINFO_FILE", tmp_path / ".keyinfo")  # absent -> v1


def _make_v2(monkeypatch, tmp_path):
    keyinfo = tmp_path / ".keyinfo"
    salt = v2.new_salt()
    _dbk, file_key = v2.derive_subkeys(v2.derive_master(PW, salt))
    v2.write_keyinfo(salt, v2.make_verification_token(file_key), path=keyinfo)
    monkeypatch.setattr(v2, "KEYINFO_FILE", keyinfo)


def test_v1_roundtrip(tmp_path, monkeypatch):
    _make_v1(monkeypatch, tmp_path)
    p = tmp_path / "f.bin"
    p.write_bytes(b"plain")
    enc.encrypt_file(str(p), PW)
    assert v2.is_v1(p.read_bytes())
    assert enc.decrypt_file_to_bytes(str(p), PW) == b"plain"


def test_v2_roundtrip(tmp_path, monkeypatch):
    _make_v2(monkeypatch, tmp_path)
    p = tmp_path / "f.bin"
    p.write_bytes(b"secret v2 content")
    enc.encrypt_file(str(p), PW)
    assert v2.is_v2(p.read_bytes())          # written as v2 on a migrated install
    assert enc.decrypt_file_to_bytes(str(p), PW) == b"secret v2 content"


def test_v1_file_still_readable_on_v2_install(tmp_path, monkeypatch):
    # Write a v1 file, then switch to a v2 install: dispatch must still read it.
    _make_v1(monkeypatch, tmp_path)
    p = tmp_path / "f.bin"
    p.write_bytes(b"legacy")
    enc.encrypt_file(str(p), PW)
    assert v2.is_v1(p.read_bytes())

    _make_v2(monkeypatch, tmp_path)
    assert enc.decrypt_file_to_bytes(str(p), PW) == b"legacy"
