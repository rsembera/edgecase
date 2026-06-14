"""
EdgeCase Encryption v2
Argon2id KDF -> HKDF subkeys -> AES-256-GCM file encryption.

Coexists with the v1 Fernet module (core/encryption.py) during migration.
v1 files begin with Fernet's 0x80 version byte; v2 files begin with 0x02,
so the two formats are unambiguously distinguishable on disk.
"""

import os

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id
from cryptography.hazmat.primitives.kdf.hkdf import HKDFExpand
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from core.config import DATA_DIR

# --- Wire format / constants ---
VERSION = 0x02            # v2 file format version byte (v1/Fernet uses 0x80)
NONCE_LEN = 12            # AES-GCM standard nonce length
SALT_LEN = 16             # Argon2id salt length
KEYINFO_MAGIC = b"ECC2"   # EdgeCase Crypto v2 key-info file magic

# Argon2id production parameters (match MailRepo): 256 MiB, t=6, p=1.
# memory_cost is in KiB, so 256 MiB = 256 * 1024 KiB.
DEFAULT_MEMORY_COST = 256 * 1024
DEFAULT_ITERATIONS = 6
DEFAULT_LANES = 1

# HKDF domain-separation labels
_DB_INFO = b"edgecase.db.v2"
_FILE_INFO = b"edgecase.file.v2"

# Verification-token plaintext (lets us check a password without SQLCipher)
_TOKEN_PLAINTEXT = b"edgecase-v2-keycheck"

KEYINFO_FILE = DATA_DIR / ".keyinfo"


def derive_master(password: str, salt: bytes, *,
                  memory_cost: int = DEFAULT_MEMORY_COST,
                  iterations: int = DEFAULT_ITERATIONS,
                  lanes: int = DEFAULT_LANES) -> bytes:
    """Derive the 32-byte master key from the password via Argon2id.

    Params are overridable so the test suite can use cheap settings;
    production always uses the module defaults.
    """
    return Argon2id(
        salt=salt, length=32,
        iterations=iterations, lanes=lanes, memory_cost=memory_cost,
    ).derive(password.encode())


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
    # Fernet tokens begin with 0x80.
    return bool(blob) and blob[0] == 0x80


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
