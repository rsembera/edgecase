"""
EdgeCase Encryption v2
Argon2id KDF -> HKDF subkeys -> AES-256-GCM file encryption.

Coexists with the v1 Fernet module (core/encryption.py) during migration.
v1 Fernet files are urlsafe-base64 and begin with 'g' (0x67) on disk; v2 files
begin with 0x02, so the two formats are unambiguously distinguishable.
"""

import os

from argon2.low_level import Type as _Argon2Type, hash_secret_raw
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDFExpand
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from core.config import DATA_DIR

# --- Wire format / constants ---
VERSION = 0x02            # v2 file format version byte (v1 Fernet leads with 0x67)
NONCE_LEN = 12            # AES-GCM standard nonce length
SALT_LEN = 16             # Argon2id salt length
KEYINFO_MAGIC = b"ECC2"   # EdgeCase Crypto v2 key-info file magic

# Argon2id production parameters (match MailRepo): 256 MiB, t=6, p=1.
# memory_cost is in KiB, so 256 MiB = 256 * 1024 KiB.
# **THESE ARE THE PRODUCTION NUMBERS AND A TEST PINS THEM** (test_kdf_cost.py).
# They are also most of the crypto tests' runtime, which is why
# argon2_parameters() below exists.
DEFAULT_MEMORY_COST = 256 * 1024
DEFAULT_ITERATIONS = 6
DEFAULT_LANES = 1

# The cheap parameters the test suite runs under. Still real Argon2id,
# still the same call site, still a genuinely encrypted install genuinely
# reopened — only the work factor changes. Nothing is mocked. (Ported from
# Daybook via MailRepo, August 16; 1 MiB / t=1 matches both siblings.)
FAST_MEMORY_COST = 1_024  # 1 MiB
FAST_ITERATIONS = 1


def argon2_parameters():
    """(memory_cost, iterations, lanes) for password derivation.

    WHY THIS IS A FUNCTION. At production strength every hash costs most
    of a second, and before this existed the cheap path was applied ad
    hoc: six test files patched derive_master locally and every other
    file paid full price — test_restore_credentials.py alone was 10s for
    25 tests. One switch, read at every derivation, replaces all of it.

    **NOT MOCKING, AND THE DISTINCTION MATTERS.** Same algorithm, same
    call site, smaller work factor. What a low cost stops proving is that
    derivation is SLOW — so test_kdf_cost.py pins the production numbers
    as literals and runs one full-cost v3 round trip with a timing floor.

    **BOTH VARIABLES ARE REQUIRED, AND THAT IS THE SAFETY.** The Argon2
    parameters are not recorded in .keyinfo — ECC2 is magic+salt+token,
    ECC3 is magic+salts+wraps, and unwrapping recomputes the KEK from
    these constants — so an install created cheaply CANNOT be opened at
    production strength, or the reverse. Getting this wrong does not
    degrade security quietly; it locks a therapist out of their practice.
    So EDGECASE_FAST_KDF alone does nothing: EDGECASE_DATA must also be
    set, which throughout EdgeCase means "this is not the real install"
    (the suite sets it to a temp dir in conftest; the testing instance
    sets it; a real install never does). Checked at call time, not
    import time, for the same reason get_state_dir() is.
    """
    if os.environ.get('EDGECASE_FAST_KDF') and os.environ.get('EDGECASE_DATA'):
        return FAST_MEMORY_COST, FAST_ITERATIONS, DEFAULT_LANES
    return DEFAULT_MEMORY_COST, DEFAULT_ITERATIONS, DEFAULT_LANES

# HKDF domain-separation labels
_DB_INFO = b"edgecase.db.v2"
_FILE_INFO = b"edgecase.file.v2"

# Verification-token plaintext (lets us check a password without SQLCipher)
_TOKEN_PLAINTEXT = b"edgecase-v2-keycheck"

KEYINFO_FILE = DATA_DIR / ".keyinfo"


def derive_master(password: str, salt: bytes) -> bytes:
    """Derive the 32-byte master key from the password via Argon2id.

    Uses argon2-cffi (the optimised reference C implementation, same as
    MailRepo). cryptography's own Argon2id was measured ~5x slower for
    identical params on the M4 (~4s vs ~0.7s), so do not switch back to it.

    Work factor comes from argon2_parameters(): production strength
    everywhere, cheap only under the two-variable test switch. The
    per-call overrides this used to take are gone — nothing legitimate
    ever passed them, and the six test files that did each carried their
    own copy of the cheap numbers, which is exactly the drift the single
    switch exists to end.
    """
    memory_cost, iterations, lanes = argon2_parameters()
    return hash_secret_raw(
        secret=password.encode(),
        salt=salt,
        time_cost=iterations,
        memory_cost=memory_cost,
        parallelism=lanes,
        hash_len=32,
        type=_Argon2Type.ID,
    )


def derive_subkeys(master: bytes):
    """Split the master into (db_key_hex, file_key) via HKDF-Expand.

    db_key_hex is the 64-char hex string for SQLCipher's raw-key PRAGMA
    (PRAGMA key = "x'<hex>'"); file_key is the 32-byte AES-256-GCM key.
    Domain-separated labels guarantee the two subkeys are independent.
    """
    db_key = HKDFExpand(algorithm=hashes.SHA256(), length=32,
                        info=_DB_INFO).derive(master)
    file_key = HKDFExpand(algorithm=hashes.SHA256(), length=32,
                          info=_FILE_INFO).derive(master)
    return db_key.hex(), file_key


def encrypt_bytes(file_key: bytes, plaintext: bytes) -> bytes:
    """Encrypt to the v2 wire format: [0x02][12-byte nonce][ct+tag].

    The version byte is bound into the GCM AAD, so a blob can't be
    reinterpreted under a different format version without failing auth.
    """
    nonce = os.urandom(NONCE_LEN)
    ct = AESGCM(file_key).encrypt(nonce, plaintext, bytes([VERSION]))
    return bytes([VERSION]) + nonce + ct


def decrypt_bytes(file_key: bytes, blob: bytes) -> bytes:
    """Decrypt a v2 blob. Raises if the version byte is wrong or auth fails."""
    if not blob or blob[0] != VERSION:
        raise ValueError("Not a v2-format blob")
    nonce = blob[1:1 + NONCE_LEN]
    ct = blob[1 + NONCE_LEN:]
    return AESGCM(file_key).decrypt(nonce, ct, bytes([VERSION]))


def is_v2(blob: bytes) -> bool:
    return bool(blob) and blob[0] == VERSION


def is_v1(blob: bytes) -> bool:
    # Fernet writes urlsafe-base64 tokens; the 0x80 format version byte inside
    # the decoded token always encodes to a leading 'g' (0x67) on disk.
    return bool(blob) and blob[0] == 0x67


# --- Key-info file: MAGIC + salt + verification token ---

def make_verification_token(file_key: bytes) -> bytes:
    """Encrypt a known constant under the file key, for password checks."""
    return encrypt_bytes(file_key, _TOKEN_PLAINTEXT)


def check_verification_token(file_key: bytes, token: bytes) -> bool:
    """True iff file_key correctly decrypts the stored verification token."""
    try:
        return decrypt_bytes(file_key, token) == _TOKEN_PLAINTEXT
    except Exception:
        return False


def new_salt() -> bytes:
    return os.urandom(SALT_LEN)


def write_keyinfo(salt: bytes, token: bytes, path=None) -> None:
    """Atomically write the key-info file (MAGIC + salt + token)."""
    path = path or KEYINFO_FILE
    blob = KEYINFO_MAGIC + salt + token
    tmp = f"{path}.tmp"
    try:
        with open(tmp, "wb") as f:
            f.write(blob)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        os.chmod(path, 0o600)
    except Exception:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
        raise


def read_keyinfo(path=None):
    """Read the key-info file, returning (salt, token). Raises on bad magic."""
    path = path or KEYINFO_FILE
    with open(path, "rb") as f:
        blob = f.read()
    if blob[:len(KEYINFO_MAGIC)] != KEYINFO_MAGIC:
        raise ValueError("Bad key-info magic")
    rest = blob[len(KEYINFO_MAGIC):]
    return rest[:SALT_LEN], rest[SALT_LEN:]


def keyinfo_exists(path=None) -> bool:
    path = path or KEYINFO_FILE
    return os.path.exists(path)


# --- Cached key derivation for a migrated (v2) install ---
# Argon2id is deliberately expensive (~0.74s); derive once per password and
# reuse across connections. Capped at 2 entries (old + new during a password
# change), mirroring core.encryption's v1 Fernet cache.
_key_cache: dict = {}


def get_keys(password: str):
    """Return (db_key_hex, file_key) for a migrated install, cached per password.

    Version-aware, and deliberately the ONLY place that branches on key-info
    format. v2 (ECC2) derives the master from the password; v3 (ECC3) unwraps a
    random master from the password wrapper. Both then take the same HKDF path,
    so every caller — core.database, core.encryption, utils.backup, tools/ —
    keeps working unchanged against either format.

    Contract difference worth knowing: on a v2 install a wrong password returns
    garbage keys (verification is a separate step against the token), whereas on
    v3 the wrapper's GCM tag fails and this RAISES ValueError. Callers that pass
    unverified passwords — Database.verify_password is the only one — must
    handle that. Raising is the better contract; v2 simply could not offer it.

    Raises if the key-info file is missing — callers gate on keyinfo_exists()
    first.
    """
    cached = _key_cache.get(password)
    if cached is not None:
        return cached
    # Lazy import: encryption_v3 imports this module for its AEAD primitives,
    # so a module-level import here would be circular.
    from core import encryption_v3 as _v3
    if _v3.keyinfo_version() == 3:
        master = _v3.unwrap_with_password(_v3.read_keyinfo(), password)
    else:
        salt, _token = read_keyinfo()
        master = derive_master(password, salt)
    keys = derive_subkeys(master)
    if len(_key_cache) >= 2:
        _key_cache.clear()
    _key_cache[password] = keys
    return keys
