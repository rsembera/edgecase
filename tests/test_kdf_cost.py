"""The KDF switch: production strength pinned, cheap path double-locked.

The suite runs Argon2id at 1 MiB / t=1 via the two-variable switch set in
conftest (EDGECASE_FAST_KDF + EDGECASE_DATA). What a cheap work factor
stops proving is that derivation is SLOW and that the production numbers
are what we say they are — so this file proves both directly, plus the
safety doctrine the switch rests on:

  The Argon2 parameters are NOT recorded in .keyinfo (ECC2 is
  magic+salt+token, ECC3 is magic+salts+wraps) — unwrapping recomputes
  the KEK from the module constants. An install created cheaply
  therefore CANNOT be opened at production strength, or the reverse:
  getting the switch wrong locks someone out of their practice. That is
  why BOTH variables are required, and why each alone must do nothing.

Ported from Daybook via MailRepo (commit 596e4e8 there), August 16.
"""
import base64
import time

import pytest

from core import encryption_v2 as v2
from core import encryption_v3 as v3


PW = "kdf-cost-password"
NEW_PW = "kdf-cost-password-2"


def _recovery_key():
    raw = base64.b32encode(b"\x07" * v3.RECOVERY_KEY_BYTES).decode()
    return "-".join(raw[i:i + 4] for i in range(0, len(raw), 4))


# ----------------------------------------------------------------------------
# Production numbers, pinned as literals
# ----------------------------------------------------------------------------

class TestProductionConstants:
    def test_production_numbers_pinned(self):
        """Asserted as LITERALS, not derived from the constants — so a
        typo in encryption_v2 cannot make both sets agree."""
        assert v2.DEFAULT_MEMORY_COST == 256 * 1024
        assert v2.DEFAULT_ITERATIONS == 6
        assert v2.DEFAULT_LANES == 1

    def test_fast_numbers_are_cheap_but_real(self):
        """The cheap path is still real Argon2id work, not zero work."""
        assert v2.FAST_MEMORY_COST == 1_024
        assert v2.FAST_ITERATIONS == 1
        assert v2.FAST_MEMORY_COST < v2.DEFAULT_MEMORY_COST
        assert v2.FAST_ITERATIONS < v2.DEFAULT_ITERATIONS


# ----------------------------------------------------------------------------
# The two-variable switch: each key alone does nothing
# ----------------------------------------------------------------------------

class TestSwitchNeedsBothKeys:
    def test_flag_alone_does_nothing(self, monkeypatch):
        monkeypatch.setenv("EDGECASE_FAST_KDF", "1")
        monkeypatch.delenv("EDGECASE_DATA", raising=False)
        assert v2.argon2_parameters() == (
            v2.DEFAULT_MEMORY_COST, v2.DEFAULT_ITERATIONS, v2.DEFAULT_LANES)

    def test_sandbox_alone_does_nothing(self, monkeypatch):
        monkeypatch.delenv("EDGECASE_FAST_KDF", raising=False)
        monkeypatch.setenv("EDGECASE_DATA", "/tmp/somewhere")
        assert v2.argon2_parameters() == (
            v2.DEFAULT_MEMORY_COST, v2.DEFAULT_ITERATIONS, v2.DEFAULT_LANES)

    def test_neither_key_is_production(self, monkeypatch):
        monkeypatch.delenv("EDGECASE_FAST_KDF", raising=False)
        monkeypatch.delenv("EDGECASE_DATA", raising=False)
        assert v2.argon2_parameters() == (
            v2.DEFAULT_MEMORY_COST, v2.DEFAULT_ITERATIONS, v2.DEFAULT_LANES)

    def test_both_keys_together_are_cheap(self):
        """conftest sets both for the whole suite; this is the state every
        other test runs under."""
        assert v2.argon2_parameters() == (
            v2.FAST_MEMORY_COST, v2.FAST_ITERATIONS, v2.DEFAULT_LANES)


# ----------------------------------------------------------------------------
# The doctrine's premise, verified rather than assumed
# ----------------------------------------------------------------------------

class TestParamsNotInKeyFile:
    def test_ecc2_is_magic_salt_token_only(self, tmp_path):
        salt = v2.new_salt()
        master = v2.derive_master(PW, salt)
        _, file_key = v2.derive_subkeys(master)
        token = v2.make_verification_token(file_key)
        path = tmp_path / ".keyinfo"
        v2.write_keyinfo(salt, token, path=path)
        blob = path.read_bytes()
        # magic + salt + token, nothing else — nowhere to record a work
        # factor, which is what makes the two-variable lock necessary.
        assert blob[:4] == b"ECC2"
        assert blob[4:4 + v2.SALT_LEN] == salt
        assert blob[4 + v2.SALT_LEN:] == token

    def test_ecc3_is_fixed_length_salts_and_wraps(self):
        master = v3.new_master()
        blob = v3.build_keyinfo(master, PW, _recovery_key())
        assert blob[:4] == b"ECC3"
        assert len(blob) == v3.KEYINFO_LEN_V3  # no variable region at all


# ----------------------------------------------------------------------------
# One full-cost round trip: production derivation, both credentials, timed
# ----------------------------------------------------------------------------

class TestFullCostRoundTrip:
    def test_v3_round_trip_at_production_strength(self, monkeypatch):
        """The one test that pays full price, and the reason it may:
        it is what proves production derivation still works AND is still
        slow. A refactor that quietly made every derivation cheap would
        leave the whole suite green — except for the floor here."""
        monkeypatch.delenv("EDGECASE_FAST_KDF", raising=False)
        assert v2.argon2_parameters()[0] == v2.DEFAULT_MEMORY_COST

        master = v3.new_master()
        key = _recovery_key()

        blob = v3.build_keyinfo(master, PW, key)

        start = time.perf_counter()
        assert v3.unwrap_with_password(blob, PW) == master
        password_unlock = time.perf_counter() - start

        # 256 MiB / t=6 costs ~0.7s on the M4; 0.25s is a generous floor
        # that still catches any cheap path (1 MiB / t=1 is ~1ms).
        assert password_unlock > 0.25, (
            f"production unlock took {password_unlock:.3f}s — "
            f"derivation has gone cheap")

        # The recovery-key KEK is HKDF, not Argon2 — deliberately cheap
        # always — so it gets a correctness assertion, not a floor.
        assert v3.unwrap_with_recovery_key(blob, key) == master

        # And a password rewrap at full cost still opens under both.
        rewrapped = v3.rewrap_password(blob, master, NEW_PW)
        assert v3.unwrap_with_password(rewrapped, NEW_PW) == master
        assert v3.unwrap_with_recovery_key(rewrapped, key) == master
