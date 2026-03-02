"""
Secrets — symmetric encryption for API keys stored in the database.

Uses Fernet (AES-128-CBC + HMAC-SHA256) from the cryptography library.
The encryption key is derived from ENCRYPTION_KEY in config.

Usage:
    from app.services.secrets import encrypt_api_key, decrypt_api_key

    encrypted = encrypt_api_key("sk-ant-...")   # store this in DB
    raw       = decrypt_api_key(encrypted)      # use this when spawning containers

MVP vs Production:
    MVP  — symmetric key stored in env var (ENCRYPTION_KEY).
    Prod — swap encrypt/decrypt to use Vault Transit or KMS; keep same interface.
"""
from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings


def _fernet() -> Fernet:
    """
    Derive a Fernet key from ENCRYPTION_KEY.
    Fernet requires a URL-safe base64-encoded 32-byte key.
    We SHA-256 hash the configured secret so any string works as input.
    """
    raw = settings.encryption_key.encode()
    key = base64.urlsafe_b64encode(hashlib.sha256(raw).digest())
    return Fernet(key)


def encrypt_api_key(plaintext: str) -> str:
    """
    Encrypt a raw API key.  Returns a base64 string safe to store in the DB.
    Raises ValueError if plaintext is empty.
    """
    if not plaintext or not plaintext.strip():
        raise ValueError("API key must not be empty")
    token: bytes = _fernet().encrypt(plaintext.encode())
    return token.decode()


def decrypt_api_key(encrypted: str) -> str:
    """
    Decrypt a stored API key.  Returns the raw plaintext.
    Raises ValueError on tampered / wrong-key ciphertext.
    """
    try:
        plaintext: bytes = _fernet().decrypt(encrypted.encode())
        return plaintext.decode()
    except InvalidToken as exc:
        raise ValueError("Failed to decrypt API key — wrong ENCRYPTION_KEY or tampered data") from exc
