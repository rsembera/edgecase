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

# Legacy salt used in versions before per-install salt was implemented
# Existing installations need this to decrypt their attachments
_LEGACY_SALT = b'EdgeCaseEqualizer2025'


def _get_salt() -> bytes:
    """Get or create per-install salt.
    
    Salt is stored in data/.salt file. For existing installations that
    have encrypted files, we use the legacy salt to maintain compatibility.
    New installations get a random salt.
    
    Detection logic:
    - If .salt file exists: use it
    - If attachments directory has files (existing install): use legacy salt
    - Otherwise (fresh install): generate new random salt
    """
    salt_file = DATA_DIR / '.salt'
    
    # If salt file exists, use it
    if salt_file.exists():
        return salt_file.read_bytes()
    
    # Check if this is an existing installation with encrypted files
    # by looking for any files in the attachments directory
    attachments_dir = DATA_DIR.parent / 'attachments'
    has_existing_attachments = False
    
    if attachments_dir.exists():
        # Check if there are any files (not just directories)
        for item in attachments_dir.rglob('*'):
            if item.is_file():
                has_existing_attachments = True
                break
    
    # Also check for encrypted assets (logo, signature)
    assets_dir = DATA_DIR.parent / 'assets'
    if assets_dir.exists():
        for item in assets_dir.iterdir():
            if item.is_file() and item.stem in ('logo', 'signature'):
                has_existing_attachments = True
                break
    
    # Ensure data directory exists
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    if has_existing_attachments:
        # Existing installation - use legacy salt for backward compatibility
        salt = _LEGACY_SALT
    else:
        # Fresh installation - generate new random salt
        salt = os.urandom(32)
    
    # Save salt for future use
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
