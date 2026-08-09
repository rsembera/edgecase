"""
EdgeCase Encryption v3 — envelope encryption with a recovery key.

v2 derives the master key directly from the password (Argon2id(password, salt)).
That makes the password the only door: forget it and the records are gone, and
changing it means re-encrypting every attachment and rebuilding the database,
because every key below the master moves.

v3 makes the master key 32 random bytes and wraps it TWICE — once under a
password-derived KEK, once under a recovery-key-derived KEK. Either wrapper
yields the same master, so db_key and file_key are derived exactly as in v2 and
NOTHING below the master needs to know v3 exists. Attachment wire format is
still v2 (0x02 version byte); only the key-info file changes, ECC2 -> ECC3.

Consequences that matter for a PHIPA install:
  * A lost password stops being terminal. CRPO retention obligations run ten
    years past last contact; "locked out of the records" is a professional
    problem, not just an inconvenience.
  * Changing the master password becomes a ~190-byte rewrap instead of a full
    file walk plus DB rebuild. That removes the rollback window from the
    operation entirely — a risk reduction, not just a feature.

The recovery key is GENERATED, never user-chosen: 160 bits of uniform entropy
means there is no password-strength guessing to defend against, so HKDF is
sufficient and unlock-by-recovery-key is instant. Argon2id would buy nothing
against a uniformly random 160-bit secret.

Threat note: a printed recovery key is a second full-access credential to
clinical records. It belongs wherever the backup media belongs — a locked
cabinet or safe — not a desk drawer.
"""

import os
import base64
import secrets

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from core import encryption_v2 as v2
from core.config import DATA_DIR


# --- Wire format / constants ---

KEYINFO_MAGIC_V3 = b"ECC3"

# 32 bytes rather than v2's 16. This is a new format with no compatibility
# constraint, so there is no reason to carry the smaller salt forward.
SALT_LEN_V3 = 32

MASTER_KEY_LEN = 32
RECOVERY_KEY_BYTES = 20   # 160 bits -> exactly 32 base32 chars, no padding
RECOVERY_KEY_GROUP = 4    # hyphenated groups of four

# HKDF domain-separation label for the recovery-key KEK.
_RECOVERY_INFO = b"edgecase.recovery.v3"

# Wrapped master = v2.encrypt_bytes output over a 32-byte plaintext:
# [0x02][12-byte nonce][32-byte ct][16-byte tag] = 61 bytes.
# Reusing the v2 AEAD deliberately: one audited primitive, one wire format.
WRAPPED_LEN = 1 + v2.NONCE_LEN + MASTER_KEY_LEN + 16

# ECC3 layout, fixed length:
#   0    4    magic "ECC3"
#   4    32   salt_pw    (Argon2id salt)
#   36   61   wrapped_pw (master under the password KEK)
#   97   32   salt_rk    (HKDF salt)
#   129  61   wrapped_rk (master under the recovery-key KEK)
_OFF_SALT_PW = len(KEYINFO_MAGIC_V3)
_OFF_WRAPPED_PW = _OFF_SALT_PW + SALT_LEN_V3
_OFF_SALT_RK = _OFF_WRAPPED_PW + WRAPPED_LEN
_OFF_WRAPPED_RK = _OFF_SALT_RK + SALT_LEN_V3
KEYINFO_LEN_V3 = _OFF_WRAPPED_RK + WRAPPED_LEN

# Base32 (RFC 4648) has no 0, 1 or 8, so these can only ever be typos for
# their lookalikes. Fixing them up costs nothing and removes the single most
# common transcription failure.
_RECOVERY_FIXUPS = str.maketrans({"0": "O", "1": "I", "8": "B"})

KEYINFO_FILE = DATA_DIR / ".keyinfo"


class RecoveryKeyError(ValueError):
    """Raised when a recovery key is malformed (as distinct from wrong)."""
    pass


# --- Recovery key: generate / format / parse ---

def generate_recovery_key() -> str:
    """Mint a fresh recovery key in display format.

    20 random bytes -> 32 base32 characters -> eight hyphenated groups of four.
    """
    return format_recovery_key(secrets.token_bytes(RECOVERY_KEY_BYTES))


def format_recovery_key(raw: bytes) -> str:
    """Render recovery-key bytes as hyphenated base32 groups."""
    encoded = base64.b32encode(raw).decode("ascii").rstrip("=")
    return "-".join(encoded[i:i + RECOVERY_KEY_GROUP]
                    for i in range(0, len(encoded), RECOVERY_KEY_GROUP))


def parse_recovery_key(text: str) -> bytes:
    """Parse a user-typed recovery key back to bytes.

    Tolerant of what people actually type: lowercase, spaces instead of
    hyphens, no hyphens at all, and 0/1/8 for O/I/B. Raises RecoveryKeyError
    on anything that cannot be a recovery key, so "you mistyped it" stays
    distinguishable from "that is the wrong key".
    """
    if not text or not text.strip():
        raise RecoveryKeyError("No recovery key provided.")

    cleaned = (text.strip().upper()
               .replace("-", "").replace(" ", "").replace("\t", "")
               .translate(_RECOVERY_FIXUPS))

    expected = len(base64.b32encode(b"\x00" * RECOVERY_KEY_BYTES).rstrip(b"="))
    if len(cleaned) != expected:
        raise RecoveryKeyError(
            f"A recovery key is {expected} characters excluding hyphens; "
            f"this one has {len(cleaned)}.")

    try:
        raw = base64.b32decode(cleaned + "=" * (-len(cleaned) % 8), casefold=False)
    except Exception:
        raise RecoveryKeyError(
            "Recovery key contains characters outside the key alphabet "
            "(A-Z and 2-7).")
    if len(raw) != RECOVERY_KEY_BYTES:
        raise RecoveryKeyError("Recovery key is the wrong length.")
    return raw


def derive_kek_from_recovery_key(raw: bytes, salt_rk: bytes) -> bytes:
    """HKDF a key-encryption key from recovery-key bytes.

    Full HKDF (extract + expand) rather than v2's expand-only: the salt makes
    two installs with the same recovery key derive different KEKs. That matters
    because recovery keys get printed, photographed and occasionally reused by
    people who should not reuse them.
    """
    return HKDF(algorithm=hashes.SHA256(), length=32,
                salt=salt_rk, info=_RECOVERY_INFO).derive(raw)


# --- Key-info blob: build / parse / unwrap / rewrap ---

def build_keyinfo(master: bytes, password: str, recovery_key: str) -> bytes:
    """Wrap the master key under both a password and a recovery key."""
    if len(master) != MASTER_KEY_LEN:
        raise ValueError(
            f"Master key must be {MASTER_KEY_LEN} bytes, got {len(master)}.")

    salt_pw = os.urandom(SALT_LEN_V3)
    salt_rk = os.urandom(SALT_LEN_V3)

    kek_pw = v2.derive_master(password, salt_pw)
    kek_rk = derive_kek_from_recovery_key(parse_recovery_key(recovery_key), salt_rk)

    blob = (KEYINFO_MAGIC_V3
            + salt_pw + v2.encrypt_bytes(kek_pw, master)
            + salt_rk + v2.encrypt_bytes(kek_rk, master))
    if len(blob) != KEYINFO_LEN_V3:
        raise ValueError(
            f"Built an ECC3 blob of {len(blob)} bytes, expected {KEYINFO_LEN_V3}.")
    return blob


def parse_keyinfo(blob: bytes) -> dict:
    """Split an ECC3 blob into its fields. Raises if malformed."""
    if blob[:4] != KEYINFO_MAGIC_V3:
        raise ValueError("Not a v3 (ECC3) key-info file.")
    if len(blob) != KEYINFO_LEN_V3:
        raise ValueError(
            f"ECC3 key-info file is {len(blob)} bytes, expected "
            f"{KEYINFO_LEN_V3}. The file may be truncated.")
    return {
        "salt_pw": blob[_OFF_SALT_PW:_OFF_WRAPPED_PW],
        "wrapped_pw": blob[_OFF_WRAPPED_PW:_OFF_SALT_RK],
        "salt_rk": blob[_OFF_SALT_RK:_OFF_WRAPPED_RK],
        "wrapped_rk": blob[_OFF_WRAPPED_RK:],
    }


def unwrap_with_password(blob: bytes, password: str) -> bytes:
    """Recover the master key using the password.

    A wrong password fails the GCM auth tag, so the wrapper doubles as the
    verification token that v2 needed a separate field for. Returns None-free:
    raises ValueError on a wrong password.
    """
    fields = parse_keyinfo(blob)
    kek = v2.derive_master(password, fields["salt_pw"])
    try:
        return v2.decrypt_bytes(kek, fields["wrapped_pw"])
    except Exception:
        raise ValueError("Invalid master password.")


def unwrap_with_recovery_key(blob: bytes, recovery_key: str) -> bytes:
    """Recover the master key using the recovery key.

    RecoveryKeyError means the input is not shaped like a recovery key;
    ValueError means it is well-formed but does not open this install.
    """
    fields = parse_keyinfo(blob)
    kek = derive_kek_from_recovery_key(
        parse_recovery_key(recovery_key), fields["salt_rk"])
    try:
        return v2.decrypt_bytes(kek, fields["wrapped_rk"])
    except Exception:
        raise ValueError("That recovery key does not open this install.")


def rewrap_password(blob: bytes, master: bytes, new_password: str) -> bytes:
    """Replace the password wrapper, leaving the recovery wrapper untouched.

    This is the whole point of the envelope: a password change rewrites 190
    bytes and genuinely revokes the old password, with no file walk, no DB
    rebuild and no rollback window. It works ONLY because the master is
    random — if the master were derived from the old password, that password
    would remain a permanent path to it no matter how often we rewrapped.
    """
    fields = parse_keyinfo(blob)
    salt_pw = os.urandom(SALT_LEN_V3)
    kek_pw = v2.derive_master(new_password, salt_pw)
    return (KEYINFO_MAGIC_V3
            + salt_pw + v2.encrypt_bytes(kek_pw, master)
            + fields["salt_rk"] + fields["wrapped_rk"])


def rewrap_recovery_key(blob: bytes, master: bytes, new_recovery_key: str) -> bytes:
    """Replace the recovery wrapper, leaving the password wrapper untouched.

    A printed recovery key is a second full-access credential to clinical
    records. If it is lost, or was stored somewhere it should not have been,
    it has to be revocable without forcing a password change.
    """
    fields = parse_keyinfo(blob)
    salt_rk = os.urandom(SALT_LEN_V3)
    kek_rk = derive_kek_from_recovery_key(
        parse_recovery_key(new_recovery_key), salt_rk)
    return (KEYINFO_MAGIC_V3
            + fields["salt_pw"] + fields["wrapped_pw"]
            + salt_rk + v2.encrypt_bytes(kek_rk, master))


# --- On-disk helpers ---

def new_master() -> bytes:
    return secrets.token_bytes(MASTER_KEY_LEN)


def is_v3_blob(blob: bytes) -> bool:
    return bool(blob) and blob[:4] == KEYINFO_MAGIC_V3


def keyinfo_version(path=None) -> int:
    """Which key-info format is on disk: 2 (ECC2) or 3 (ECC3).

    Callers that only need "is this still v1" should keep using
    v2.keyinfo_exists() — its meaning is unchanged by v3.
    """
    path = path or KEYINFO_FILE
    with open(path, "rb") as f:
        magic = f.read(4)
    if magic == KEYINFO_MAGIC_V3:
        return 3
    if magic == v2.KEYINFO_MAGIC:
        return 2
    raise ValueError(
        "Key-info file has no recognised magic. It may have been written by an "
        "incompatible version of EdgeCase, or may be corrupt.")


def read_keyinfo(path=None) -> bytes:
    """Raw bytes of the ECC3 key-info file (validated)."""
    path = path or KEYINFO_FILE
    with open(path, "rb") as f:
        blob = f.read()
    parse_keyinfo(blob)
    return blob


def write_keyinfo(blob: bytes, path=None) -> None:
    """Atomically replace the key-info file with a validated ECC3 blob.

    Same crash-safe pattern as v2.write_keyinfo — temp file, fsync, replace —
    plus a directory fsync, which is the step usually missed: without it the
    rename itself can vanish on power loss even though the data was synced.
    """
    parse_keyinfo(blob)
    path = path or KEYINFO_FILE
    tmp = f"{path}.v3tmp"
    try:
        with open(tmp, "wb") as f:
            f.write(blob)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        os.chmod(path, 0o600)
        dir_fd = os.open(os.path.dirname(str(path)), os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except Exception:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
        raise
