"""Field-level encryption at rest (Fernet = AES-128-CBC + HMAC-SHA256).

Sensitive columns (account / wallet numbers, phone numbers, TIN, trade licence no.) use the
``EncryptedString`` column type, so they are encrypted before they reach SQLite and decrypted
only when loaded by the application.

Key management: ``FIELD_ENCRYPTION_KEY`` env var. In production a missing key is fatal. In
dev/demo a key is generated once into ``data/.dev_field_key`` so local restarts keep working;
that file is git-ignored and must never be used for real data.
"""
from __future__ import annotations

import logging
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.types import String, TypeDecorator

from sme_copilot.config import get_settings

log = logging.getLogger(__name__)
_PREFIX = "enc:v1:"


@lru_cache
def _fernet() -> Fernet:
    s = get_settings()
    key = s.field_encryption_key.strip()
    if not key:
        if s.app_env == "production":
            raise RuntimeError("FIELD_ENCRYPTION_KEY is required in production")
        path = s.data_dir / ".dev_field_key"
        if path.exists():
            key = path.read_text().strip()
        else:
            key = Fernet.generate_key().decode()
            path.write_text(key)
            log.warning("Generated a DEV field-encryption key at %s (not for real data)", path)
    return Fernet(key.encode())


def reset_crypto_cache() -> None:
    _fernet.cache_clear()


def encrypt(value: str | None) -> str | None:
    if value is None or value == "":
        return value
    return _PREFIX + _fernet().encrypt(value.encode()).decode()


def decrypt(token: str | None) -> str | None:
    if token is None or not token.startswith(_PREFIX):
        return token
    try:
        return _fernet().decrypt(token[len(_PREFIX):].encode()).decode()
    except InvalidToken:
        log.error("could not decrypt a field (wrong FIELD_ENCRYPTION_KEY?)")
        return "[undecryptable]"


class EncryptedString(TypeDecorator):
    impl = String
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return encrypt(value)

    def process_result_value(self, value, dialect):
        return decrypt(value)
