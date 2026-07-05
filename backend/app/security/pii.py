"""PII Detection — regex-based detector for emails, phones, IDs, etc."""

import hashlib
import re

import structlog

logger = structlog.get_logger(__name__)


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
        """掩盖文本中的 PII"""
        if pii_type:
            pattern = self.PATTERNS.get(pii_type)
            if pattern:
                return re.sub(pattern, self._get_mask(pii_type), text)
        else:
            for pii_type, pattern in self.PATTERNS.items():
                text = re.sub(pattern, self._get_mask(pii_type), text)

        return text

    def _get_mask(self, pii_type: str) -> str:
        """获取掩码字符串"""
        masks = {
            "email": "***@***.***",
            "phone_cn": "1**********",
            "phone_us": "+1**********",
            "id_card_cn": "***************X",
            "bank_card": "****-****-****-****",
            "ip_address": "*.*.*.*",
        }
        return masks.get(pii_type, "***")


# ── PII Detection Database (PostgreSQL via asyncpg) ──


async def log_pii_detection(
    document_id: str,
    pii_type: str,
    value: str,
    original_length: int,
    masked_value: str,
    action_taken: str = "mask",
):
    """记录 PII 检测结果到 PostgreSQL (asyncpg)."""
    from app.database.connection import get_db_pool

    pool = get_db_pool()
    if pool is None:
        logger.warning("DATABASE_URL not set, skipping PII detection log")
        return

    value_hash = hashlib.sha256(value.encode()).hexdigest()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO pii_detections (document_id, pii_type, value_hash, original_length, masked_value, action_taken)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            document_id, pii_type, value_hash, original_length, masked_value, action_taken,
        )
    logger.debug("pii_detection_logged", pii_type=pii_type, document_id=document_id)
