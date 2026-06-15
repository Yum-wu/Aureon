"""PII Detection �� regex-based detector for emails, phones, IDs, etc."""

import hashlib
import re


class PIIDetector:
    """PII �����"""

    # �������ʽģʽ
    PATTERNS = {
        "email": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
        "phone_cn": r"1[3-9]\d{9}",
        "phone_us": r"\+?1?\d{10,12}",
        "id_card_cn": r"\d{17}[\dXx]",
        "bank_card": r"\d{16,19}",
        "ip_address": r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}",
    }

    def detect(self, text: str) -> list[dict]:
        """����ı��е� PII"""
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
        """�����ı��е� PII"""
        if pii_type:
            pattern = self.PATTERNS.get(pii_type)
            if pattern:
                return re.sub(pattern, self._get_mask(pii_type), text)
        else:
            for pii_type, pattern in self.PATTERNS.items():
                text = re.sub(pattern, self._get_mask(pii_type), text)

        return text

    def _get_mask(self, pii_type: str) -> str:
        """��ȡ��������"""
        masks = {
            "email": "***@***.***",
            "phone_cn": "1**********",
            "phone_us": "+1**********",
            "id_card_cn": "***************X",
            "bank_card": "****-****-****-****",
            "ip_address": "*.*.*.*",
        }
        return masks.get(pii_type, "***")


# ���� PII Detection Database ����

def init_pii_detection_table():
    """��ʼ�� PII ����"""
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
    """��¼ PII ���"""
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
