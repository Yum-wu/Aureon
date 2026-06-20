"""RBAC: Roles, Permissions, JWT token utilities, and FastAPI role dependencies."""

import enum
import os
from datetime import datetime, timezone

import structlog

logger = structlog.get_logger()


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


# Role �� set of Permissions
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


# ���� JWT token utilities ����

_JWT_SECRET: str | None = None
_JWT_ALGORITHM = "HS256"
_JWT_EXPIRY_HOURS = 24


def _get_jwt_secret() -> str:
    """Lazily resolve the JWT signing secret from environment.

    Raises RuntimeError if JWT_SECRET is not set (no insecure default).
    """
    global _JWT_SECRET
    if _JWT_SECRET is None:
        _JWT_SECRET = os.environ.get("JWT_SECRET")
        if not _JWT_SECRET:
            raise RuntimeError(
                "JWT_SECRET environment variable is required. "
                "Set it before starting the application."
            )
    return _JWT_SECRET


def create_access_token(data: dict) -> str:
    """Create a signed JWT access token."""
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
    """Decode and verify a JWT token."""
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


# 闭包注册表：require_role 每次创建 _role_checker 时注册，
# 供测试 conftest.py 直接获取闭包引用，无需遍历 app.routes（FastAPI 0.137+ routes 为 tree 结构）
_ROLE_CHECKERS: list = []


def require_role(min_role: UserRole):
    """FastAPI dependency that enforces a minimum :class:`UserRole`."""
    from fastapi import Request
    from app.exceptions import AuthenticationError, AuthorizationError

    async def _role_checker(request: Request) -> dict:
        from app.config import settings

        # Hard block: dev bypass forbidden on production platforms
        _is_prod_platform = os.environ.get("RAILWAY_ENVIRONMENT") == "production"
        if settings.auth.environment == "dev" and _is_prod_platform:
            logger.critical("security.rbac_dev_bypass_blocked_in_prod")
            raise AuthenticationError("Authentication required")

        # Dev bypass (only on non-production platforms)
        if settings.auth.environment == "dev" and not settings.api_auth_key:
            return {"sub": "dev-user", "role": "ADMIN", "_role": UserRole.ADMIN}
        
        # API key authentication (X-API-Key header) — grants ADMIN access
        api_key = request.headers.get("X-API-Key", "")
        if api_key and settings.api_auth_key and api_key == settings.api_auth_key:
            return {"sub": "api-key-user", "role": "ADMIN", "_role": UserRole.ADMIN}
        
        # Extract token directly from Authorization header
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

    _ROLE_CHECKERS.append(_role_checker)
    return _role_checker
