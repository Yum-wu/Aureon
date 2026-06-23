"""Security Hardening - SSO, PII Detection, Rate Limiting, RBAC

EXPERIMENTAL: PII detection and SSO not connected to core paths.
Encryption utilities (encrypt_secret/decrypt_secret) ARE used by SSO.

All public symbols are re-exported from sub-modules for backward compatibility.
"""

from pydantic import BaseModel

# ── RBAC ──
from app.security.rbac import (
    UserRole,
    Permission,
    ROLE_PERMISSIONS,
    create_access_token,
    verify_token,
    get_user_role,
    has_permission,
    require_role,
)

# ── Encryption ──
from app.security.encryption import (
    encrypt_secret,
    decrypt_secret,
    rotate_token,
)

# ── Token Revocation (S11) ──
from app.security.token_revocation import (
    revoke_token,
    is_token_revoked,
    cleanup_memory_revoked,
)

# ── PII Detection ──
from app.security.pii import (
    PIIDetector,
    init_pii_detection_table,
    log_pii_detection,
)

# ── SSO ──
from app.security.sso import (
    SSOProvider,
    SSOConfig,
    init_sso_providers_table,
    create_sso_provider,
    list_sso_providers,
    get_sso_provider,
    delete_sso_provider,
)


# ── Rate Limiting Models (lightweight, kept here) ──

class RateLimitConfig(BaseModel):
    """速率限制配置"""
    enabled: bool = True
    requests_per_minute: int = 60
    requests_per_hour: int = 1000
    tokens_per_minute: int = 100000
    tokens_per_hour: int = 1000000


class RateLimitEntry(BaseModel):
    """速率限制条目"""
    key: str
    requests: int = 0
    tokens: int = 0
    window_start: float = 0


__all__ = [
    # RBAC
    "UserRole", "Permission", "ROLE_PERMISSIONS",
    "create_access_token", "verify_token", "get_user_role",
    "has_permission", "require_role",
    # Encryption
    "encrypt_secret", "decrypt_secret", "rotate_token",
    # Token Revocation
    "revoke_token", "is_token_revoked", "cleanup_memory_revoked",
    # PII
    "PIIDetector", "init_pii_detection_table", "log_pii_detection",
    # SSO
    "SSOProvider", "SSOConfig",
    "init_sso_providers_table", "create_sso_provider",
    "list_sso_providers", "get_sso_provider", "delete_sso_provider",
    # Rate Limiting
    "RateLimitConfig", "RateLimitEntry",
]
