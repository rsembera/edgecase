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


def encrypt_file(filepath: str, password: str) -> None:
    """Encrypt a file in place.

    Writes to a temp file in the same directory and atomically replaces
    the original (os.replace), so a crash mid-write can never leave a
    truncated file with the plaintext already destroyed.
    """
    fernet = _get_fernet(password)

    with open(filepath, 'rb') as f:
        data = f.read()

    encrypted = fernet.encrypt(data)

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


def decrypt_file_to_bytes(filepath: str, password: str) -> bytes:
    """Decrypt a file and return the plaintext bytes."""
    fernet = _get_fernet(password)
    
    with open(filepath, 'rb') as f:
        encrypted = f.read()
    
    return fernet.decrypt(encrypted)
