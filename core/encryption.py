"""
EdgeCase Encryption Module
Handles file encryption/decryption using Fernet (AES-128)
"""

import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


# Fixed salt - okay because password is already strong and unique per install
SALT = b'EdgeCaseEqualizer2025'


def _get_fernet(password: str) -> Fernet:
    """Derive encryption key from password and return Fernet instance."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=SALT,
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