"""Knowledge Intelligence - Document Version Control & Export"""
from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel, Field
import structlog

logger = structlog.get_logger()


class DocumentVersion(BaseModel):
    """文档版本"""
    id: Optional[int] = None
    document_id: str = Field(..., description="文档 ID")
    version: int = Field(..., description="版本号")
    content_hash: str = Field(..., description="内容哈希")
    content_preview: Optional[str] = None
    changes_summary: Optional[str] = None
    created_by: Optional[str] = None
    created_at: Optional[str] = None


class ExportRequest(BaseModel):
    """导出请求"""
    export_type: str = Field(..., description="query_history/analytics/knowledge_snapshot")
    format: str = Field("csv", description="csv/json/pdf")
    date_range_days: int = Field(30, ge=1, le=365)
    workspace_id: Optional[str] = None


class ExportRecord(BaseModel):
    """导出记录"""
    id: Optional[int] = None
    export_type: str
    format: str
    file_path: Optional[str] = None
    file_size_bytes: int = 0
    status: str = "pending"  # pending/completed/failed
    requested_by: Optional[str] = None
    created_at: Optional[str] = None
    completed_at: Optional[str] = None


def init_knowledge_tables():
    """初始化知识智能表"""
    from app.memory.db import get_db

    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS document_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id TEXT NOT NULL,
            version INTEGER NOT NULL,
            content_hash TEXT NOT NULL,
            content_preview TEXT,
            changes_summary TEXT,
            created_by TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS export_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            export_type TEXT NOT NULL,
            format TEXT NOT NULL,
            file_path TEXT,
            file_size_bytes INTEGER DEFAULT 0,
            status TEXT DEFAULT 'pending',
            requested_by TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_document_versions_doc ON document_versions(document_id)
    """)
    conn.commit()


def create_document_version(version: DocumentVersion) -> int:
    """创建文档版本"""
    from app.memory.db import get_db

    conn = get_db()
    now = datetime.now(timezone.utc).isoformat()

    cursor = conn.execute(
        """
        INSERT INTO document_versions (document_id, version, content_hash, content_preview, changes_summary, created_by, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            version.document_id,
            version.version,
            version.content_hash,
            version.content_preview,
            version.changes_summary,
            version.created_by,
            now,
        ),
    )
    conn.commit()

    return cursor.lastrowid


def get_document_versions(document_id: str, limit: int = 10) -> list[DocumentVersion]:
    """获取文档版本历史"""
    from app.memory.db import get_db

    conn = get_db()
    rows = conn.execute(
        """
        SELECT * FROM document_versions
        WHERE document_id = ?
        ORDER BY version DESC
        LIMIT ?
        """,
        (document_id, limit),
    ).fetchall()

    return [
        DocumentVersion(
            id=row["id"],
            document_id=row["document_id"],
            version=row["version"],
            content_hash=row["content_hash"],
            content_preview=row["content_preview"],
            changes_summary=row["changes_summary"],
            created_by=row["created_by"],
            created_at=row["created_at"],
        )
        for row in rows
    ]


def get_latest_version(document_id: str) -> Optional[DocumentVersion]:
    """获取最新版本"""
    from app.memory.db import get_db

    conn = get_db()
    row = conn.execute(
        """
        SELECT * FROM document_versions
        WHERE document_id = ?
        ORDER BY version DESC
        LIMIT 1
        """,
        (document_id,),
    ).fetchone()

    if row is None:
        return None

    return DocumentVersion(
        id=row["id"],
        document_id=row["document_id"],
        version=row["version"],
        content_hash=row["content_hash"],
        content_preview=row["content_preview"],
        changes_summary=row["changes_summary"],
        created_by=row["created_by"],
        created_at=row["created_at"],
    )


def create_export_record(record: ExportRecord) -> int:
    """创建导出记录"""
    from app.memory.db import get_db

    conn = get_db()
    now = datetime.now(timezone.utc).isoformat()

    cursor = conn.execute(
        """
        INSERT INTO export_records (export_type, format, file_path, file_size_bytes, status, requested_by, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            record.export_type,
            record.format,
            record.file_path,
            record.file_size_bytes,
            "pending",
            record.requested_by,
            now,
        ),
    )
    conn.commit()

    return cursor.lastrowid


def complete_export(record_id: int, status: str = "completed", file_path: str = None, file_size: int = 0):
    """完成导出"""
    from app.memory.db import get_db

    conn = get_db()
    now = datetime.now(timezone.utc).isoformat()

    conn.execute(
        """
        UPDATE export_records
        SET status = ?, file_path = ?, file_size_bytes = ?, completed_at = ?
        WHERE id = ?
        """,
        (status, file_path, file_size, now, record_id),
    )
    conn.commit()


def get_export_records(limit: int = 10) -> list[ExportRecord]:
    """获取导出记录"""
    from app.memory.db import get_db

    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM export_records ORDER BY created_at DESC LIMIT ?",
        (limit,),
    ).fetchall()

    return [
        ExportRecord(
            id=row["id"],
            export_type=row["export_type"],
            format=row["format"],
            file_path=row["file_path"],
            file_size_bytes=row["file_size_bytes"],
            status=row["status"],
            requested_by=row["requested_by"],
            created_at=row["created_at"],
            completed_at=row["completed_at"],
        )
        for row in rows
    ]
