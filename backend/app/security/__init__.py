"""Security Hardening - SSO, PII Detection, Rate Limiting, RBAC

EXPERIMENTAL: PII detection and SSO not connected to core paths.
Encryption utilities (encrypt_secret/decrypt_secret) ARE used by SSO.
"""
import enum
import functools
import hashlib
import hmac
import json
import os
import re
import time
from datetime import datetime, timezone
from typing import Optional

import structlog
from pydantic import BaseModel, Field

from app.common import mask_secret

logger = structlog.get_logger()


# ── RBAC: Roles, Permissions & Role-Permission Matrix ──


class UserRole(enum.IntEnum):
    """Roles with ascending privilege level (used for comparison)."""
    VIEWER = 0
    EDITOR = 1
    ADMIN = 2


class Permission(enum.Enum):
    """Fine-grained permissions that map to roles."""
    READ = "read"
    WRITE = "write"
    UPLOAD = "upload"
    INDEX = "index"
    ADMIN = "admin"


# Role → set of Permissions
ROLE_PERMISSIONS: dict[UserRole, set[Permission]] = {
    UserRole.VIEWER: {Permission.READ},
    UserRole.EDITOR: {Permission.READ, Permission.WRITE, Permission.UPLOAD},
    UserRole.ADMIN: {
        Permission.READ,
        Permission.WRITE,
        Permission.UPLOAD,
        Permission.INDEX,
        Permission.ADMIN,
    },
}

# ── JWT token utilities ──

_JWT_SECRET: str | None = None
_JWT_ALGORITHM = "HS256"
_JWT_EXPIRY_HOURS = 24


def _get_jwt_secret() -> str:
    """Lazily resolve the JWT signing secret from environment.

    Raises RuntimeError if JWT_SECRET is not set (no insecure default).
    """
    global _JWT_SECRET
    if _JWT_SECRET is None:
        import os
        _JWT_SECRET = os.environ.get("JWT_SECRET")
        if not _JWT_SECRET:
            raise RuntimeError(
                "JWT_SECRET environment variable is required. "
                "Set it before starting the application."
            )
    return _JWT_SECRET


def create_access_token(data: dict) -> str:
    """Create a signed JWT access token.

    Args:
        data: Payload dict. Must contain ``sub`` (subject / user id) and
              ``role`` (a :class:`UserRole` value or string).

    Returns:
        Encoded JWT string.
    """
    try:
        import jwt
    except ImportError:
        raise RuntimeError("PyJWT is required: pip install PyJWT>=2.8")

    secret = _get_jwt_secret()
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    to_encode.setdefault("iat", int(now.timestamp()))
    to_encode.setdefault(
        "exp", int((now.timestamp()) + _JWT_EXPIRY_HOURS * 3600)
    )
    return jwt.encode(to_encode, secret, algorithm=_JWT_ALGORITHM)


def verify_token(token: str) -> dict:
    """Decode and verify a JWT token.

    Returns:
        Decoded payload dict.

    Raises:
        AuthenticationError: If the token is invalid or expired.
    """
    try:
        import jwt
    except ImportError:
        raise RuntimeError("PyJWT is required: pip install PyJWT>=2.8")

    from app.exceptions import AuthenticationError

    secret = _get_jwt_secret()
    try:
        payload = jwt.decode(token, secret, algorithms=[_JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise AuthenticationError("Token has expired")
    except jwt.InvalidTokenError as exc:
        raise AuthenticationError(f"Invalid token: {exc}")
    return payload


def get_user_role(token_payload: dict) -> UserRole:
    """Extract :class:`UserRole` from a decoded token payload."""
    role_str = token_payload.get("role", "VIEWER")
    if isinstance(role_str, UserRole):
        return role_str
    try:
        return UserRole[role_str.upper()]
    except KeyError:
        return UserRole.VIEWER


def has_permission(role: UserRole, perm: Permission) -> bool:
    """Check whether *role* grants *perm*."""
    return perm in ROLE_PERMISSIONS.get(role, set())


def require_role(min_role: UserRole):
    """FastAPI dependency that enforces a minimum :class:`UserRole`.

    Usage in a route::

        @router.post("/admin/action")
        async def admin_action(user=Depends(require_role(UserRole.ADMIN))):
            ...

    The dependency reads ``Authorization: Bearer <jwt>`` from the request
    header, decodes the token, and compares the role.
    """
    from fastapi import Request
    from app.exceptions import AuthenticationError, AuthorizationError

    async def _role_checker(request: Request) -> dict:
        # Skip RBAC when API_AUTH_KEY is not configured (dev mode)
        from app.config import settings
        if not settings.api_auth_key:
            return {"sub": "dev-user", "role": "ADMIN", "_role": UserRole.ADMIN}

        # Extract token from Authorization header directly
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
        else:
            raise AuthenticationError("Missing or invalid Authorization header")

        if not token:
            raise AuthenticationError("Token is required")

        payload = verify_token(token)
        user_role = get_user_role(payload)

        if user_role < min_role:
            raise AuthorizationError(
                f"Insufficient permissions: requires {min_role.name}, got {user_role.name}"
            )

        payload["_role"] = user_role
        return payload

    return _role_checker


# -- Secret Encryption (Fernet symmetric encryption) --

_fernet = None


def _get_fernet():
    """Lazy-init Fernet cipher. Key from ENCRYPTION_KEY env or auto-generate."""
    global _fernet
    if _fernet is not None:
        return _fernet
    try:
        from cryptography.fernet import Fernet
        key = os.environ.get("ENCRYPTION_KEY")
        if not key:
            key = Fernet.generate_key()
            logger.warning("ENCRYPTION_KEY not set, generated ephemeral key (lost on restart)")
        _fernet = Fernet(key.encode() if isinstance(key, str) else key)
    except ImportError:
        logger.warning("cryptography not installed, secret encryption disabled")
        _fernet = False
    return _fernet if _fernet is not False else None


def encrypt_secret(value: str | None) -> str | None:
    """Encrypt a secret value with Fernet. Returns base64 ciphertext.

    Raises RuntimeError if Fernet is not available (cryptography not installed).
    """
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
    """Decrypt a Fernet-encrypted secret. Returns plaintext.

    Raises RuntimeError if Fernet is not available.
    Raises ValueError if decryption fails (wrong key or corrupted data).
    """
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


# ── PII Detection ──

class PIIDetector:
    """PII 检测器"""

    # 正则表达式模式
    PATTERNS = {
        "email": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
        "phone_cn": r"1[3-9]\d{9}",
        "phone_us": r"\+?1?\d{10,12}",
        "id_card_cn": r"\d{17}[\dXx]",
        "bank_card": r"\d{16,19}",
        "ip_address": r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}",
    }

    def detect(self, text: str) -> list[dict]:
        """检测文本中的 PII"""
        results = []

        for pii_type, pattern in self.PATTERNS.items():
            matches = re.finditer(pattern, text)
            for match in matches:
                results.append({
                    "type": pii_type,
                    "value": match.group(),
                    "start": match.start(),
                    "end": match.end(),
                })

        return results

    def mask(self, text: str, pii_type: str = None) -> str:
        """脱敏文本中的 PII"""
        if pii_type:
            pattern = self.PATTERNS.get(pii_type)
            if pattern:
                return re.sub(pattern, self._get_mask(pii_type), text)
        else:
            for pii_type, pattern in self.PATTERNS.items():
                text = re.sub(pattern, self._get_mask(pii_type), text)

        return text

    def _get_mask(self, pii_type: str) -> str:
        """获取脱敏掩码"""
        masks = {
            "email": "***@***.***",
            "phone_cn": "1**********",
            "phone_us": "+1**********",
            "id_card_cn": "***************X",
            "bank_card": "****-****-****-****",
            "ip_address": "*.*.*.*",
        }
        return masks.get(pii_type, "***")


# ── SSO Models ──

class SSOProvider(BaseModel):
    """SSO 提供商配置"""
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


# ── Rate Limiting Models ──

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


# ── PII Detection Database ──

def init_pii_detection_table():
    """初始化 PII 检测表"""
    from app.memory.db import get_db

    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pii_detections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id TEXT,
            pii_type TEXT NOT NULL,
            value_hash TEXT NOT NULL,
            original_length INTEGER,
            masked_value TEXT,
            action_taken TEXT DEFAULT 'mask',
            detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_pii_detections_document ON pii_detections(document_id)
    """)
    conn.commit()


def log_pii_detection(
    document_id: str,
    pii_type: str,
    value: str,
    original_length: int,
    masked_value: str,
    action_taken: str = "mask",
):
    """记录 PII 检测"""
    import hashlib
    from app.memory.db import get_db

    conn = get_db()
    value_hash = hashlib.sha256(value.encode()).hexdigest()

    conn.execute(
        """
        INSERT INTO pii_detections (document_id, pii_type, value_hash, original_length, masked_value, action_taken)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (document_id, pii_type, value_hash, original_length, masked_value, action_taken),
    )
    conn.commit()


# ── SSO Database ──

def init_sso_providers_table():
    """初始化 SSO 提供商表"""
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
    """创建 SSO 提供商"""
    from app.memory.db import get_db
    from datetime import datetime, timezone

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


def list_sso_providers() -> list[SSOProvider]:
    """列出所有 SSO 提供商"""
    from app.memory.db import get_db

    conn = get_db()
    rows = conn.execute("SELECT * FROM sso_providers ORDER BY created_at DESC").fetchall()

    return [
        SSOProvider(
            id=row["id"],
            name=row["name"],
            provider_type=row["provider_type"],
            client_id=row["client_id"],
            client_secret=mask_secret(decrypt_secret(row["client_secret"])),
            metadata_url=row["metadata_url"],
            enabled=bool(row["enabled"]),
            created_at=row["created_at"],
        )
        for row in rows
    ]


def get_sso_provider(name: str) -> Optional[SSOProvider]:
    """获取单个 SSO 提供商（client_secret 脱敏）"""
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
        client_secret=mask_secret(decrypt_secret(row["client_secret"])),
        metadata_url=row["metadata_url"],
        enabled=bool(row["enabled"]),
        created_at=row["created_at"],
    )


def delete_sso_provider(name: str) -> bool:
    """删除 SSO 提供商"""
    from app.memory.db import get_db

    conn = get_db()
    cursor = conn.execute("DELETE FROM sso_providers WHERE name = ?", (name,))
    conn.commit()

    return cursor.rowcount > 0
