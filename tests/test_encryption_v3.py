"""Crypto v3 envelope — recovery keys, both doors, and credential revocation.

The v3 key-info file wraps a random master twice: once under the password, once
under a printed recovery key. These tests pin the three properties the design
actually rests on:

  1. Both doors yield the SAME master, so db_key/file_key are identical either
     way and nothing below the master can tell which door was used.
  2. Rewrapping one credential genuinely REVOKES the old one while leaving the
     other intact. This is the property a password-derived master cannot offer.
  3. ECC2 and ECC3 installs stay distinguishable on disk, while
     v2.keyinfo_exists() keeps its old meaning of "not v1".

The fast_kdf fixture swaps Argon2id to cheap params, mirroring
test_migrate_crypto. encryption_v3 calls v2.derive_master through the module,
so patching it there covers v3 as well.
"""
import os

import pytest

from core import encryption_v2 as v2
from core import encryption_v3 as v3

PW = "synth-master-pw"
NEW_PW = "synth-rotated-pw"


@pytest.fixture(autouse=True)
def fast_kdf(monkeypatch):
    real = v2.derive_master
    monkeypatch.setattr(
        v2, "derive_master",
        lambda pw, salt, **kw: real(pw, salt, memory_cost=64, iterations=1, lanes=1),
    )
    v2._key_cache.clear()


@pytest.fixture
def envelope():
    """A freshly built ECC3 install: (blob, master, recovery_key)."""
    master = v3.new_master()
    rk = v3.generate_recovery_key()
    return v3.build_keyinfo(master, PW, rk), master, rk


# --- Recovery key encoding ---

def test_recovery_key_shape():
    rk = v3.generate_recovery_key()
    assert rk.count("-") == 7
    assert len(rk.replace("-", "")) == 32
    assert v3.format_recovery_key(v3.parse_recovery_key(rk)) == rk


def test_recovery_keys_are_distinct():
    keys = {v3.generate_recovery_key() for _ in range(50)}
    assert len(keys) == 50


@pytest.mark.parametrize("mangle", [
    str.lower,
    lambda s: s.replace("-", ""),
    lambda s: s.replace("-", " "),
    lambda s: f"  {s}\t",
    lambda s: s.replace("-", "").lower(),
    lambda s: s.replace("O", "0").replace("I", "1").replace("B", "8"),
])
def test_parse_tolerates_realistic_transcription(mangle):
    """Lowercase, lost hyphens, stray whitespace, and 0/1/8 for O/I/B.

    Base32 excludes 0, 1 and 8 entirely, so those substitutions are
    unambiguously typos and correcting them cannot mask a real key.
    """
    rk = v3.generate_recovery_key()
    assert v3.parse_recovery_key(mangle(rk)) == v3.parse_recovery_key(rk)


@pytest.mark.parametrize("bad", ["", "   ", "ABCD-EFGH", "!" * 32, "A" * 31, "A" * 33])
def test_malformed_recovery_key_is_distinguishable_from_wrong(bad):
    """RecoveryKeyError ("you mistyped it") must not be confused with a
    well-formed key that simply does not open this install."""
    with pytest.raises(v3.RecoveryKeyError):
        v3.parse_recovery_key(bad)


# --- The envelope: both doors ---

def test_blob_matches_declared_layout(envelope):
    blob, _master, _rk = envelope
    assert len(blob) == v3.KEYINFO_LEN_V3 == 190
    assert v3.is_v3_blob(blob)


def test_both_doors_yield_the_same_master(envelope):
    blob, master, rk = envelope
    assert v3.unwrap_with_password(blob, PW) == master
    assert v3.unwrap_with_recovery_key(blob, rk) == master


def test_subkeys_identical_regardless_of_door(envelope):
    """The point of the envelope: nothing below the master knows which
    credential opened it, so attachments and SQLCipher are untouched."""
    blob, master, rk = envelope
    via_pw = v2.derive_subkeys(v3.unwrap_with_password(blob, PW))
    via_rk = v2.derive_subkeys(v3.unwrap_with_recovery_key(blob, rk))
    assert via_pw == via_rk == v2.derive_subkeys(master)


def test_wrong_password_rejected(envelope):
    blob, _master, _rk = envelope
    with pytest.raises(ValueError):
        v3.unwrap_with_password(blob, "not the password")


def test_wrong_recovery_key_rejected(envelope):
    blob, _master, _rk = envelope
    with pytest.raises(ValueError):
        v3.unwrap_with_recovery_key(blob, v3.generate_recovery_key())


# --- Rewrapping: revocation is the whole point ---

def test_password_rotation_revokes_the_old_password(envelope):
    """A v2 password change re-encrypts everything precisely so the old
    password stops working. The envelope must give the same guarantee from a
    190-byte rewrap — if the old password still opened the install, the cheap
    rotation would be a silent downgrade of the guarantee users think they
    have."""
    blob, master, rk = envelope
    rotated = v3.rewrap_password(blob, master, NEW_PW)

    assert v3.unwrap_with_password(rotated, NEW_PW) == master
    with pytest.raises(ValueError):
        v3.unwrap_with_password(rotated, PW)


def test_password_rotation_leaves_the_recovery_key_working(envelope):
    blob, master, rk = envelope
    rotated = v3.rewrap_password(blob, master, NEW_PW)
    assert v3.unwrap_with_recovery_key(rotated, rk) == master


def test_recovery_key_rotation_revokes_the_old_key(envelope):
    """A printed recovery key is a second full-access credential to clinical
    records. If it is lost or was stored badly it has to be revocable without
    forcing a password change."""
    blob, master, rk = envelope
    rk2 = v3.generate_recovery_key()
    rotated = v3.rewrap_recovery_key(blob, master, rk2)

    assert v3.unwrap_with_recovery_key(rotated, rk2) == master
    with pytest.raises(ValueError):
        v3.unwrap_with_recovery_key(rotated, rk)


def test_recovery_key_rotation_leaves_the_password_working(envelope):
    blob, master, rk = envelope
    rotated = v3.rewrap_recovery_key(blob, master, v3.generate_recovery_key())
    assert v3.unwrap_with_password(rotated, PW) == master


def test_rotations_compose(envelope):
    """Rotate both credentials in sequence; each rewrap must preserve the
    untouched half of the envelope."""
    blob, master, rk = envelope
    rk2 = v3.generate_recovery_key()
    final = v3.rewrap_recovery_key(
        v3.rewrap_password(blob, master, NEW_PW), master, rk2)

    assert v3.unwrap_with_password(final, NEW_PW) == master
    assert v3.unwrap_with_recovery_key(final, rk2) == master
    with pytest.raises(ValueError):
        v3.unwrap_with_password(final, PW)
    with pytest.raises(ValueError):
        v3.unwrap_with_recovery_key(final, rk)


def test_salts_are_fresh_on_every_rewrap(envelope):
    blob, master, _rk = envelope
    a = v3.parse_keyinfo(blob)
    b = v3.parse_keyinfo(v3.rewrap_password(blob, master, NEW_PW))
    assert a["salt_pw"] != b["salt_pw"]
    assert a["wrapped_pw"] != b["wrapped_pw"]
    assert a["salt_rk"] == b["salt_rk"]      # untouched half preserved verbatim
    assert a["wrapped_rk"] == b["wrapped_rk"]


# --- On-disk: both key-info formats must stay distinguishable ---

@pytest.fixture
def ecc2_file(tmp_path):
    """A genuine ECC2 key-info written by the existing v2 code path."""
    path = tmp_path / ".keyinfo_v2"
    salt = v2.new_salt()
    _db_key, file_key = v2.derive_subkeys(v2.derive_master(PW, salt))
    v2.write_keyinfo(salt, v2.make_verification_token(file_key), path=path)
    return path


@pytest.fixture
def ecc3_file(tmp_path, envelope):
    path = tmp_path / ".keyinfo_v3"
    v3.write_keyinfo(envelope[0], path=path)
    return path


def test_version_detection_across_both_formats(ecc2_file, ecc3_file):
    assert v3.keyinfo_version(path=ecc2_file) == 2
    assert v3.keyinfo_version(path=ecc3_file) == 3


def test_keyinfo_exists_still_means_not_v1(ecc2_file, ecc3_file):
    """Eight call sites treat keyinfo_exists() as "not a v1 install". v3 must
    not quietly change that meaning underneath them."""
    assert v2.keyinfo_exists(path=ecc2_file)
    assert v2.keyinfo_exists(path=ecc3_file)


def test_v2_reader_rejects_a_v3_file(ecc3_file):
    """v2.read_keyinfo checks the ECC2 magic, so a v3 install can never be
    silently misread as v2 with a garbage salt."""
    with pytest.raises(ValueError):
        v2.read_keyinfo(path=ecc3_file)


def test_write_read_round_trip(ecc3_file, envelope):
    assert v3.read_keyinfo(path=ecc3_file) == envelope[0]


def test_keyinfo_written_0600(ecc3_file):
    assert (os.stat(ecc3_file).st_mode & 0o777) == 0o600


def test_unrecognised_magic_rejected(tmp_path):
    path = tmp_path / ".keyinfo_bad"
    path.write_bytes(b"XXXX" + b"\x00" * 186)
    with pytest.raises(ValueError):
        v3.keyinfo_version(path=path)


@pytest.mark.parametrize("trim", [1, 61, 100])
def test_truncated_blob_rejected(envelope, trim):
    """A short read or torn write must fail loudly rather than unwrap
    something wrong."""
    with pytest.raises(ValueError):
        v3.parse_keyinfo(envelope[0][:-trim])


def test_write_refuses_a_non_v3_blob(tmp_path):
    """write_keyinfo validates before replacing the file, so a bug upstream
    cannot leave an unopenable install behind."""
    with pytest.raises(ValueError):
        v3.write_keyinfo(b"ECC2" + b"\x00" * 100, path=tmp_path / ".keyinfo")
    assert not (tmp_path / ".keyinfo").exists()


def test_build_rejects_wrong_length_master():
    with pytest.raises(ValueError):
        v3.build_keyinfo(b"\x00" * 16, PW, v3.generate_recovery_key())


# --- The read path: an ECC3 install must be openable through get_keys ---

@pytest.fixture
def live_keyinfo(tmp_path, monkeypatch):
    """Point BOTH modules' default key-info path at a temp file.

    get_keys() and verify_password() read the live path with no argument, so
    exercising the real read path means relocating it rather than passing one in.
    """
    path = tmp_path / ".keyinfo"
    monkeypatch.setattr(v2, "KEYINFO_FILE", path)
    monkeypatch.setattr(v3, "KEYINFO_FILE", path)
    v2._key_cache.clear()
    yield path
    v2._key_cache.clear()


def test_get_keys_opens_a_v3_install(live_keyinfo, envelope):
    """The whole point of branching inside get_keys: an ECC3 install yields
    exactly the subkeys the master implies, with no caller changes."""
    blob, master, _rk = envelope
    v3.write_keyinfo(blob, path=live_keyinfo)
    assert v2.get_keys(PW) == v2.derive_subkeys(master)


def test_get_keys_still_opens_a_v2_install(live_keyinfo):
    """Regression guard: the v2 path must survive the branch being added."""
    salt = v2.new_salt()
    expected = v2.derive_subkeys(v2.derive_master(PW, salt))
    v2.write_keyinfo(salt, v2.make_verification_token(expected[1]), path=live_keyinfo)
    assert v2.get_keys(PW) == expected


def test_get_keys_raises_on_wrong_password_under_v3(live_keyinfo, envelope):
    """v2 returned garbage for a wrong password; v3 can and should refuse.
    Database.verify_password is the one caller that passes unverified input."""
    v3.write_keyinfo(envelope[0], path=live_keyinfo)
    with pytest.raises(ValueError):
        v2.get_keys("not the password")


def test_wrong_password_is_not_cached(live_keyinfo, envelope):
    v3.write_keyinfo(envelope[0], path=live_keyinfo)
    with pytest.raises(ValueError):
        v2.get_keys("not the password")
    assert "not the password" not in v2._key_cache


def test_keys_survive_a_password_rotation(live_keyinfo, envelope):
    """The envelope's real payoff: rotating the password leaves db_key and
    file_key untouched, so nothing needs re-encrypting or rekeying."""
    blob, master, _rk = envelope
    v3.write_keyinfo(blob, path=live_keyinfo)
    before = v2.get_keys(PW)

    v3.write_keyinfo(v3.rewrap_password(blob, master, NEW_PW), path=live_keyinfo)
    v2._key_cache.clear()

    assert v2.get_keys(NEW_PW) == before
