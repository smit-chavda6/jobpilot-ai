"""Field-level encryption (Fernet: AES-128-CBC + HMAC-SHA256).

Envelope encryption: each value is encrypted with a random data key, and the data key is
encrypted with the master key from ENCRYPTION_KEY. Rotating the master key only requires
re-wrapping data keys (see docs/runbook.md).
"""

from __future__ import annotations

import base64
import json

from cryptography.fernet import Fernet

from app.config import get_settings


def _master() -> Fernet:
    return Fernet(get_settings().encryption_key.encode())


def encrypt_field(plaintext: str) -> str:
    data_key = Fernet.generate_key()
    wrapped_key = _master().encrypt(data_key)
    ciphertext = Fernet(data_key).encrypt(plaintext.encode())
    blob = {"k": wrapped_key.decode(), "c": ciphertext.decode(), "v": 1}
    return base64.urlsafe_b64encode(json.dumps(blob).encode()).decode()


def decrypt_field(token: str) -> str:
    blob = json.loads(base64.urlsafe_b64decode(token.encode()))
    data_key = _master().decrypt(blob["k"].encode())
    return Fernet(data_key).decrypt(blob["c"].encode()).decode()
