"""Symmetric encryption for sensitive data at rest.

Uses Fernet (AES-128-CBC + HMAC-SHA256) derived from the app secret key.
Values are prefixed with 'enc:' for backwards compatibility — plaintext
values without the prefix are returned as-is during the migration period.
"""

from __future__ import annotations

import base64
import hashlib
import logging

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        from backend.config import settings
        key = base64.urlsafe_b64encode(
            hashlib.sha256(settings.secret_key.encode()).digest()
        )
        _fernet = Fernet(key)
    return _fernet


def encrypt(plaintext: str) -> str:
    """Encrypt a string. Returns 'enc:' prefixed ciphertext."""
    if not plaintext:
        return plaintext
    return "enc:" + _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    """Decrypt a string. Plaintext without 'enc:' prefix is returned as-is."""
    if not ciphertext:
        return ciphertext
    if not ciphertext.startswith("enc:"):
        return ciphertext  # Not encrypted — backwards compatible
    try:
        return _get_fernet().decrypt(ciphertext[4:].encode()).decode()
    except InvalidToken:
        logger.error("Failed to decrypt value — key may have changed")
        return ""
