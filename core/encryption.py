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
    
    return salt


def _get_fernet(password: str) -> Fernet:
    """Derive encryption key from password and return Fernet instance."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=_get_salt(),
        iterations=480000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
    return Fernet(key)


def encrypt_file(filepath: str, password: str) -> None:
    """Encrypt a file in place."""
    fernet = _get_fernet(password)
    
    with open(filepath, 'rb') as f:
        data = f.read()
    
    encrypted = fernet.encrypt(data)
    
    with open(filepath, 'wb') as f:
        f.write(encrypted)


def decrypt_file_to_bytes(filepath: str, password: str) -> bytes:
    """Decrypt a file and return the plaintext bytes."""
    fernet = _get_fernet(password)
    
    with open(filepath, 'rb') as f:
        encrypted = f.read()
    
    return fernet.decrypt(encrypted)
