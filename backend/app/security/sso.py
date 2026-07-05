"""SSO provider models and database operations for Single Sign-On providers.

PostgreSQL asyncpg backend.
"""

from datetime import datetime, timezone
from typing import Optional

import structlog
from pydantic import BaseModel, Field

from app.common import mask_secret
from app.security.encryption import encrypt_secret, decrypt_secret

logger = structlog.get_logger()


class SSOProvider(BaseModel):
    """SSO 提供商模型"""
    id: Optional[int] = None
    name: str = Field(..., description="提供商名称")
    provider_type: str = Field(..., description="SAML/OIDC/LDAP")
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    metadata_url: Optional[str] = None
    enabled: bool = True
    created_at: Optional[str] = None


class SSOConfig(BaseModel):
    """SSO 配置"""
    enabled: bool = False
    provider: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    metadata_url: Optional[str] = None
    allowed_domains: list[str] = []


# ── SSO Database (PostgreSQL via asyncpg) ──


async def _get_pool():
    from app.database.connection import get_db_pool
    pool = get_db_pool()
    if pool is None:
        raise RuntimeError("DATABASE_URL not configured — cannot access SSO providers")
    return pool


async def create_sso_provider(provider: SSOProvider) -> SSOProvider:
    """创建 SSO 提供商"""
    pool = await _get_pool()
    now = datetime.now(timezone.utc)

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO sso_providers (name, provider_type, client_id, client_secret, metadata_url, enabled, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING id, name, provider_type, client_id, client_secret, metadata_url, enabled, created_at
            """,
            provider.name,
            provider.provider_type,
            provider.client_id,
            encrypt_secret(provider.client_secret),
            provider.metadata_url,
            provider.enabled,
            now,
        )

    return SSOProvider(
        id=row["id"],
        name=row["name"],
        provider_type=row["provider_type"],
        client_id=row["client_id"],
        client_secret=provider.client_secret,
        metadata_url=row["metadata_url"],
        enabled=row["enabled"],
        created_at=row["created_at"].isoformat() if hasattr(row["created_at"], "isoformat") else row["created_at"],
    )


def _decrypt_client_secret(client_secret: Optional[str]) -> str:
    """Decrypt and mask a stored SSO client_secret, with graceful fallback."""
    try:
        return mask_secret(decrypt_secret(client_secret))
    except (ValueError, RuntimeError) as exc:
        logger.warning(
            "sso_provider_decrypt_failed",
            client_secret_prefix=(client_secret or "")[:8] + "***" if client_secret else None,
            error=str(exc),
        )
        return "****[unreadable]****"


def _row_to_provider(row) -> SSOProvider:
    """Convert asyncpg Record to SSOProvider."""
    return SSOProvider(
        id=row["id"],
        name=row["name"],
        provider_type=row["provider_type"],
        client_id=row["client_id"],
        client_secret=_decrypt_client_secret(row["client_secret"]),
        metadata_url=row["metadata_url"],
        enabled=bool(row["enabled"]),
        created_at=row["created_at"].isoformat() if hasattr(row["created_at"], "isoformat") else row["created_at"],
    )


async def list_sso_providers() -> list[SSOProvider]:
    """列出所有 SSO 提供商 (client_secret 已脱敏)."""
    pool = await _get_pool()

    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM sso_providers ORDER BY created_at DESC")

    return [_row_to_provider(r) for r in rows]


async def get_sso_provider(name: str) -> Optional[SSOProvider]:
    """获取指定名称的 SSO 提供商 (client_secret 已脱敏)."""
    pool = await _get_pool()

    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM sso_providers WHERE name = $1", name)

    if row is None:
        return None
    return _row_to_provider(row)


async def delete_sso_provider(name: str) -> bool:
    """删除 SSO 提供商"""
    pool = await _get_pool()

    async with pool.acquire() as conn:
        result = await conn.execute("DELETE FROM sso_providers WHERE name = $1", name)

    # asyncpg DELETE returns "DELETE N"
    count = int(result.split()[-1]) if result else 0
    return count > 0


async def get_all_sso_providers_raw() -> list[dict]:
    """获取所有 SSO provider 的 id + client_secret（用于密钥轮换，不脱敏）."""
    pool = await _get_pool()

    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT id, client_secret FROM sso_providers")

    return [dict(r) for r in rows]


async def update_sso_provider_secret(provider_id: int, new_ciphertext: str) -> None:
    """更新 SSO provider 的 client_secret（用于密钥轮换）."""
    pool = await _get_pool()

    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE sso_providers SET client_secret = $1 WHERE id = $2",
            new_ciphertext, provider_id,
        )
