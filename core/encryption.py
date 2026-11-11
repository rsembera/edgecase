"""
EdgeCase Encryption Module
Handles file encryption/decryption using Fernet (AES-128)
"""

import base64
import os
from pathlib import Path
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from core.config import DATA_DIR


def _get_salt() -> bytes:
    """Get or create per-install salt.
    
    Salt is stored in data/.salt file. Generated once on first use,
    then reused for all subsequent encryption operations.
    """
    salt_file = DATA_DIR / '.salt'
    
    # If salt file exists, use it
    if salt_file.exists():
        return salt_file.read_bytes()
    
    # Generate new random salt for fresh installation
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    salt = os.urandom(32)
    salt_file.write_bytes(salt)
    os.chmod(salt_file, 0o600)  # Owner read/write only
    
    return salt


# Cache of derived Fernet instances, keyed by password. PBKDF2 at 480k
# iterations is deliberately slow (~0.5s), and re-deriving it for every
# encrypt/decrypt call adds that cost to each file operation. Single-user
# app: at most two passwords are ever live at once (old + new during a
# password change), so the cache is capped at 2 entries and stale entries
# are dropped when a new password is cached.
_fernet_cache: dict = {}


def _get_fernet(password: str) -> Fernet:
    """Derive encryption key from password and return Fernet instance.

    The derived Fernet is cached in module memory so the expensive KDF
    runs once per password instead of once per file operation.
    """
    cached = _fernet_cache.get(password)
    if cached is not None:
        return cached

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=_get_salt(),
        iterations=480000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
    fernet = Fernet(key)

    # Keep at most 2 entries (old + new during a password change);
    # clear stale entries before caching a new password.
    if len(_fernet_cache) >= 2:
        _fernet_cache.clear()
    _fernet_cache[password] = fernet
    return fernet


def forget_keys() -> None:
    """Drop every cached key and the password strings they are filed under.

    Called when the practice is locked (logout, timeout, window close).
    The caches exist so key derivation runs once per session; left alone
    they kept the master password and the database key in memory for as
    long as the process lived, locked or not.
    """
    from core import encryption_v2 as _v2
    _fernet_cache.clear()
    _v2._key_cache.clear()


def encrypt_file(filepath: str, password: str) -> None:
    """Encrypt a file in place.

    Writes to a temp file in the same directory and atomically replaces
    the original (os.replace), so a crash mid-write can never leave a
    truncated file with the plaintext already destroyed.
    """
    with open(filepath, 'rb') as f:
        data = f.read()

    # On a migrated (v2) install write v2 (Argon2id-derived file key,
    # AES-256-GCM); otherwise v1 Fernet, so un-migrated installs are unchanged.
    from core import encryption_v2 as _v2
    if _v2.keyinfo_exists():
        _db_key_hex, file_key = _v2.get_keys(password)
        encrypted = _v2.encrypt_bytes(file_key, data)
    else:
        encrypted = _get_fernet(password).encrypt(data)

    tmp_path = f'{filepath}.tmp'
    try:
        with open(tmp_path, 'wb') as f:
            f.write(encrypted)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, filepath)
    except Exception:
        # Don't leave a partial temp file behind
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        raise


def upgrade_legacy_file(filepath: str, password: str) -> str:
    """Bring one v1 (Fernet) file on a migrated install up to the current
    format, in place and atomically.

    The encryption upgrade walks a fixed set of files, and for a while that
    set missed the logo and signature (core.config.is_practice_asset), so a
    migrated install can still be holding them as Fernet blobs. They keep
    opening only as long as the master password never changes, because the
    Fernet key is derived from the password itself. This re-encrypts such a
    file under the current file key, which survives password changes.

    Returns 'upgraded', 'current' (already v2), 'not_migrated' (a v1
    install: nothing to do), 'unrecognised' (not an encrypted file), or
    'failed' (a Fernet blob the current password no longer opens).
    """
    from core import encryption_v2 as _v2
    if not _v2.keyinfo_exists():
        return 'not_migrated'
    with open(filepath, 'rb') as f:
        blob = f.read()
    if _v2.is_v2(blob):
        return 'current'
    if not _v2.is_v1(blob):
        return 'unrecognised'
    # _get_salt() would mint a NEW salt if the file were missing; a new
    # salt cannot open an old blob, so do not create one for the attempt.
    if not (DATA_DIR / '.salt').exists():
        return 'failed'
    try:
        plaintext = _get_fernet(password).decrypt(blob)
    except Exception:
        return 'failed'

    _db_key_hex, file_key = _v2.get_keys(password)
    encrypted = _v2.encrypt_bytes(file_key, plaintext)
    tmp_path = f'{filepath}.tmp'
    try:
        with open(tmp_path, 'wb') as f:
            f.write(encrypted)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, filepath)
    except Exception:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        raise
    return 'upgraded'


def decrypt_file_to_bytes(filepath: str, password: str) -> bytes:
    """Decrypt a file and return the plaintext bytes.

    Version-aware: a v2 blob (0x02 prefix) is decrypted with the Argon2id-
    derived file key; anything else uses the v1 Fernet path. Both stay readable
    during the migration bake period.
    """
    with open(filepath, 'rb') as f:
        blob = f.read()

    from core import encryption_v2 as _v2
    if _v2.is_v2(blob):
        _db_key_hex, file_key = _v2.get_keys(password)
        return _v2.decrypt_bytes(file_key, blob)
    return _get_fernet(password).decrypt(blob)
