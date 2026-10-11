"""Field-level credential encryption at rest using Fernet."""

import base64

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from apps.api.config import settings


def _get_fernet() -> Fernet:
    """Derives a deterministic 32-byte Fernet key from configured secret string."""
    key = settings.FIELD_ENCRYPTION_KEY.encode()
    if len(key) == 44 and key.endswith(b"="):
        try:
            return Fernet(key)
        except Exception:
            pass

    # Fallback to key derivation if raw passphrase is provided
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"jobpilot_static_salt_for_field_enc",
        iterations=100000,
    )
    derived = base64.urlsafe_b64encode(kdf.derive(key))
    return Fernet(derived)


def encrypt_field(plaintext: str) -> str:
    """Encrypts sensitive plaintext into an ASCII ciphertext string."""
    if not plaintext:
        return ""
    f = _get_fernet()
    return f.encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_field(ciphertext: str) -> str:
    """Decrypts ciphertext back into plaintext."""
    if not ciphertext:
        return ""
    f = _get_fernet()
    return f.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
