"""Encryption utilities — Fernet symmetric encryption for secrets.

支持 MultiFernet 密钥轮换：ENCRYPTION_KEY 环境变量支持逗号分隔的多密钥。
第一个密钥用于加密，所有密钥可用于解密（向后兼容）。
"""

import os

import structlog

logger = structlog.get_logger()

_fernet = None


def _get_fernet():
    """Lazy-init Fernet cipher. 支持多密钥轮换（MultiFernet）。

    从 ENCRYPTION_KEY 环境变量读取密钥（支持逗号分隔的多密钥）。
    第一个密钥用于加密，所有密钥可用于解密（向后兼容）。
    dev 模式下自动生成临时密钥。
    cryptography 未安装时返回 None（_fernet = False 哨兵）。
    """
    global _fernet
    # _fernet 可能是 False（cryptography 未安装的哨兵），需要跳过
    if _fernet is not None and _fernet is not False:
        return _fernet
    try:
        from cryptography.fernet import Fernet, MultiFernet

        key_str = os.environ.get("ENCRYPTION_KEY", "")
        # 支持逗号分隔的多密钥（密钥轮换）
        keys = [k.strip() for k in key_str.split(",") if k.strip()]
        if not keys:
            from app.config import settings
            if settings.auth.environment != "dev":
                raise RuntimeError(
                    "ENCRYPTION_KEY must be set in production. "
                    "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
                )
            keys = [Fernet.generate_key().decode()]
            logger.warning("ENCRYPTION_KEY not set, generated ephemeral key (lost on restart) — dev mode only")
        # 构造 MultiFernet：第一个密钥用于加密，所有密钥可用于解密
        fernet_keys = [Fernet(k.encode() if isinstance(k, str) else k) for k in keys]
        _fernet = MultiFernet(fernet_keys)
    except ImportError:
        logger.warning("cryptography not installed, secret encryption disabled")
        _fernet = False
    return _fernet if _fernet is not False else None


def encrypt_secret(value: str | None) -> str | None:
    """Encrypt a secret value with Fernet. Returns base64 ciphertext.

    使用 MultiFernet 的第一个密钥进行加密。
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

    使用 MultiFernet 尝试所有密钥进行解密（向后兼容）。
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


async def rotate_token(old_key: str) -> int:
    """批量迁移历史数据：用旧密钥加密的 SSO provider client_secret 用新密钥重新加密。

    遍历 sso_providers 表，用 old_key 解密后用当前 MultiFernet 的第一个密钥重新加密。
    返回迁移计数。

    注意：此函数为 async 以便在异步上下文中调用，SQLite 操作本身是同步的。
    """
    from cryptography.fernet import Fernet

    from app.memory.db import get_db
    from app.security.sso import init_sso_providers_table

    init_sso_providers_table()
    conn = get_db()

    # 读取所有 SSO provider
    rows = conn.execute("SELECT id, client_secret FROM sso_providers").fetchall()

    # 用旧密钥构造 Fernet
    old_fernet = Fernet(old_key.encode() if isinstance(old_key, str) else old_key)

    migrated = 0
    for row in rows:
        old_ciphertext = row["client_secret"]
        if not old_ciphertext:
            continue

        try:
            # 用旧密钥解密
            plaintext = old_fernet.decrypt(old_ciphertext.encode()).decode()
            # 用新密钥重新加密（MultiFernet 的第一个密钥）
            new_ciphertext = encrypt_secret(plaintext)
            # 更新数据库
            conn.execute(
                "UPDATE sso_providers SET client_secret = ? WHERE id = ?",
                (new_ciphertext, row["id"]),
            )
            migrated += 1
        except Exception as exc:
            logger.warning(
                "rotate_token_failed",
                provider_id=row["id"],
                error=str(exc),
            )

    conn.commit()
    logger.info("rotate_token_completed", migrated=migrated, total=len(rows))
    return migrated
