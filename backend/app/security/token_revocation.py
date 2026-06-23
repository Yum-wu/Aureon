"""JWT Token 吊销机制 — Redis denylist + 内存降级。

使用 Redis 存储吊销的 JWT jti claim，TTL = token 剩余有效期。
Redis 不可用时降级到内存 dict（带过期清理）。
"""

import hashlib
import threading
import time

import structlog

logger = structlog.get_logger()

# 内存降级存储：jti -> expiry_timestamp
_memory_revoked: dict[str, float] = {}
_memory_lock = threading.Lock()

# Redis 键前缀
_REDIS_KEY_PREFIX = "revoked:"

# 默认 TTL（当 token 没有 exp claim 时使用）
_DEFAULT_TTL_SECONDS = 24 * 3600


async def revoke_token(token: str) -> bool:
    """吊销一个 JWT token。

    解码 JWT 提取 jti claim（如果没有 jti，用 token 的 hash）。
    在 Redis 中设置 revoked:{jti} 键，TTL = token 剩余有效期。
    Redis 不可用时降级到内存 dict。

    返回是否成功。
    """
    try:
        import jwt
    except ImportError:
        logger.error("PyJWT not installed, cannot revoke token")
        return False

    # 解码 JWT（不验证签名，只提取 claims）
    try:
        payload = jwt.decode(token, options={"verify_signature": False})
    except jwt.InvalidTokenError as exc:
        logger.warning("revoke_token_decode_failed", error=str(exc))
        return False

    # 提取 jti，如果没有则用 token 的 hash
    jti = payload.get("jti")
    if not jti:
        jti = hashlib.sha256(token.encode()).hexdigest()

    # 计算 TTL（token 剩余有效期）
    exp = payload.get("exp")
    if exp:
        ttl = max(int(exp) - int(time.time()), 1)
    else:
        ttl = _DEFAULT_TTL_SECONDS

    # 尝试 Redis
    try:
        from app.cache.connection import get_async_redis

        redis = get_async_redis()
        if redis is not None:
            await redis.setex(f"{_REDIS_KEY_PREFIX}{jti}", ttl, "1")
            logger.info("token_revoked_redis", jti=jti, ttl=ttl)
            return True
    except Exception as exc:
        logger.warning("token_revoke_redis_failed", error=str(exc))

    # 降级到内存
    with _memory_lock:
        _memory_revoked[jti] = time.time() + ttl
    logger.info("token_revoked_memory", jti=jti, ttl=ttl)
    return True


async def is_token_revoked(jti: str) -> bool:
    """检查 JWT jti 是否已吊销。

    检查 Redis 中是否存在 revoked:{jti}。
    Redis 不可用时检查内存 dict。

    返回是否已吊销。
    """
    if not jti:
        return False

    # 尝试 Redis
    try:
        from app.cache.connection import get_async_redis

        redis = get_async_redis()
        if redis is not None:
            exists = await redis.exists(f"{_REDIS_KEY_PREFIX}{jti}")
            return bool(exists)
    except Exception as exc:
        logger.warning("token_check_redis_failed", error=str(exc))

    # 降级到内存
    with _memory_lock:
        expiry = _memory_revoked.get(jti)
        if expiry is None:
            return False
        if time.time() > expiry:
            # 已过期，清理
            _memory_revoked.pop(jti, None)
            return False
        return True


def cleanup_memory_revoked() -> int:
    """清理内存 dict 中过期的条目。

    返回清理的条目数。
    """
    now = time.time()
    with _memory_lock:
        expired = [jti for jti, exp in _memory_revoked.items() if now > exp]
        for jti in expired:
            _memory_revoked.pop(jti, None)
    if expired:
        logger.info("memory_revoked_cleanup", count=len(expired))
    return len(expired)
