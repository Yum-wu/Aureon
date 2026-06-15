"""SSO �� models and database operations for Single Sign-On providers."""

from datetime import datetime, timezone
from typing import Optional

import structlog
from pydantic import BaseModel, Field

from app.common import mask_secret
from app.security.encryption import encrypt_secret, decrypt_secret

logger = structlog.get_logger()


class SSOProvider(BaseModel):
    """SSO �ṩ������"""
    id: Optional[int] = None
    name: str = Field(..., description="�ṩ������")
    provider_type: str = Field(..., description="SAML/OIDC/LDAP")
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    metadata_url: Optional[str] = None
    enabled: bool = True
    created_at: Optional[str] = None


class SSOConfig(BaseModel):
    """SSO ����"""
    enabled: bool = False
    provider: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    metadata_url: Optional[str] = None
    allowed_domains: list[str] = []


# ���� SSO Database ����

def init_sso_providers_table():
    """��ʼ�� SSO �ṩ�̱�"""
    from app.memory.db import get_db

    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sso_providers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            provider_type TEXT NOT NULL,
            client_id TEXT,
            client_secret TEXT,
            metadata_url TEXT,
            enabled BOOLEAN DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()


def create_sso_provider(provider: SSOProvider) -> SSOProvider:
    """���� SSO �ṩ��"""
    from app.memory.db import get_db

    conn = get_db()
    now = datetime.now(timezone.utc).isoformat()

    cursor = conn.execute(
        """
        INSERT INTO sso_providers (name, provider_type, client_id, client_secret, metadata_url, enabled, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            provider.name,
            provider.provider_type,
            provider.client_id,
            encrypt_secret(provider.client_secret),
            provider.metadata_url,
            provider.enabled,
            now,
        ),
    )
    conn.commit()

    return SSOProvider(
        id=cursor.lastrowid,
        name=provider.name,
        provider_type=provider.provider_type,
        client_id=provider.client_id,
        client_secret=provider.client_secret,
        metadata_url=provider.metadata_url,
        enabled=provider.enabled,
        created_at=now,
    )


def _decrypt_client_secret(client_secret: Optional[str]) -> str:
    """Decrypt and mask a stored SSO client_secret, with graceful fallback.

    On decryption failure (e.g. ENCRYPTION_KEY was rotated and the old ciphertext
    is no longer readable, or the ciphertext is corrupted) this returns a
    placeholder so the list/get endpoint does not 500 for the whole table.
    The error is logged so operators can investigate.
    """
    try:
        return mask_secret(decrypt_secret(client_secret))
    except (ValueError, RuntimeError) as exc:
        logger.warning(
            "sso_provider_decrypt_failed",
            client_secret_prefix=(client_secret or "")[:8] + "***" if client_secret else None,
            error=str(exc),
        )
        return "****[unreadable]****"


def list_sso_providers() -> list[SSOProvider]:
    """List all SSO providers (client_secret is masked)."""
    from app.memory.db import get_db

    conn = get_db()
    rows = conn.execute("SELECT * FROM sso_providers ORDER BY created_at DESC").fetchall()

    return [
        SSOProvider(
            id=row["id"],
            name=row["name"],
            provider_type=row["provider_type"],
            client_id=row["client_id"],
            client_secret=_decrypt_client_secret(row["client_secret"]),
            metadata_url=row["metadata_url"],
            enabled=bool(row["enabled"]),
            created_at=row["created_at"],
        )
        for row in rows
    ]


def get_sso_provider(name: str) -> Optional[SSOProvider]:
    """Get a named SSO provider (client_secret is masked)."""
    from app.memory.db import get_db

    conn = get_db()
    row = conn.execute(
        "SELECT * FROM sso_providers WHERE name = ?",
        (name,),
    ).fetchone()

    if row is None:
        return None

    return SSOProvider(
        id=row["id"],
        name=row["name"],
        provider_type=row["provider_type"],
        client_id=row["client_id"],
        client_secret=_decrypt_client_secret(row["client_secret"]),
        metadata_url=row["metadata_url"],
        enabled=bool(row["enabled"]),
        created_at=row["created_at"],
    )


def delete_sso_provider(name: str) -> bool:
    """ɾ�� SSO �ṩ��"""
    from app.memory.db import get_db

    conn = get_db()
    cursor = conn.execute("DELETE FROM sso_providers WHERE name = ?", (name,))
    conn.commit()

    return cursor.rowcount > 0
