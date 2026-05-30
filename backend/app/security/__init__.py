"""Security Hardening - SSO, PII Detection, Rate Limiting"""
import re
from typing import Optional
from pydantic import BaseModel, Field
import structlog

logger = structlog.get_logger()


def _mask_secret(value: str | None, show_chars: int = 4) -> str | None:
    if not value:
        return value
    if len(value) <= show_chars:
        return "****"
    return value[:show_chars] + "****"


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
            provider.client_secret,
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
            client_secret=_mask_secret(row["client_secret"]),
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
        client_secret=_mask_secret(row["client_secret"]),
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
