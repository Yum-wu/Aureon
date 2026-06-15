"""Encryption utilities �� Fernet symmetric encryption for secrets."""

import os

import structlog

logger = structlog.get_logger()

_fernet = None


def _get_fernet():
    """Lazy-init Fernet cipher. Key from ENCRYPTION_KEY env or auto-generate in dev only."""
    global _fernet
    # Note: _fernet may be `False` (sentinel for "cryptography missing"); the
    # early-return must skip it so the fallback `None` is returned below.
    if _fernet is not None and _fernet is not False:
        return _fernet
    try:
        from cryptography.fernet import Fernet
        key = os.environ.get("ENCRYPTION_KEY")
        if not key:
            from app.config import settings
            if settings.auth.environment != "dev":
                raise RuntimeError(
                    "ENCRYPTION_KEY must be set in production. "
                    "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
                )
            key = Fernet.generate_key()
            logger.warning("ENCRYPTION_KEY not set, generated ephemeral key (lost on restart) — dev mode only")
        _fernet = Fernet(key.encode() if isinstance(key, str) else key)
    except ImportError:
        logger.warning("cryptography not installed, secret encryption disabled")
        _fernet = False
    return _fernet if _fernet is not False else None


def encrypt_secret(value: str | None) -> str | None:
    """Encrypt a secret value with Fernet. Returns base64 ciphertext."""
    if not value:
        return value
    f = _get_fernet()
    if f is None:
        raise RuntimeError(
            "Secret encryption unavailable: cryptography package not installed. "
            "Install it with: pip install cryptography"
        )
    return f.encrypt(value.encode()).decode()


def decrypt_secret(value: str | None) -> str | None:
    """Decrypt a Fernet-encrypted secret. Returns plaintext."""
    if not value:
        return value
    f = _get_fernet()
    if f is None:
        raise RuntimeError(
            "Secret decryption unavailable: cryptography package not installed. "
            "Install it with: pip install cryptography"
        )
    try:
        return f.decrypt(value.encode()).decode()
    except Exception as exc:
        raise ValueError(
            f"Failed to decrypt secret (wrong key or corrupted data): {exc}"
        ) from exc
