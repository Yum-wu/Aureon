"""Feature Flag System - 数据库模型和 API

EXPERIMENTAL: Not connected to core paths. Models/Routes exist but unused by production flow.
"""
import hashlib
import sqlite3
import json
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class FlagStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"


class FeatureFlag(BaseModel):
    id: Optional[int] = None
    name: str = Field(..., min_length=1, max_length=100, description="Flag 名称")
    description: Optional[str] = None
    status: FlagStatus = FlagStatus.DRAFT
    enabled: bool = False
    workspace_id: Optional[str] = None
    user_id: Optional[str] = None
    percentage: int = Field(0, ge=0, le=100, description="灰度百分比")
    conditions: Optional[dict] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class FeatureFlagCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    enabled: bool = False
    percentage: int = Field(0, ge=0, le=100)
    conditions: Optional[dict] = None


class FeatureFlagUpdate(BaseModel):
    description: Optional[str] = None
    status: Optional[FlagStatus] = None
    enabled: Optional[bool] = None
    percentage: Optional[int] = Field(None, ge=0, le=100)
    conditions: Optional[dict] = None


class FeatureFlagResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    status: str
    enabled: bool
    percentage: int
    conditions: Optional[dict]
    created_at: str
    updated_at: str


# ── Database Operations ──

def init_feature_flags_table():
    """初始化 Feature Flag 表"""
    from app.memory.db import get_db

    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS feature_flags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            description TEXT,
            status TEXT DEFAULT 'draft',
            enabled BOOLEAN DEFAULT 0,
            percentage INTEGER DEFAULT 0,
            conditions TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_feature_flags_name ON feature_flags(name)
    """)
    conn.commit()


def create_flag(flag: FeatureFlagCreate) -> FeatureFlagResponse:
    """创建新的 Feature Flag"""
    from app.memory.db import get_db

    conn = get_db()
    now = datetime.now(timezone.utc).isoformat()

    cursor = conn.execute(
        """
        INSERT INTO feature_flags (name, description, status, enabled, percentage, conditions, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            flag.name,
            flag.description,
            FlagStatus.DRAFT.value,
            flag.enabled,
            flag.percentage,
            json.dumps(flag.conditions) if flag.conditions else None,
            now,
            now,
        ),
    )
    conn.commit()

    return FeatureFlagResponse(
        id=cursor.lastrowid,
        name=flag.name,
        description=flag.description,
        status=FlagStatus.DRAFT.value,
        enabled=flag.enabled,
        percentage=flag.percentage,
        conditions=flag.conditions,
        created_at=now,
        updated_at=now,
    )


def get_flag_by_name(name: str) -> Optional[FeatureFlagResponse]:
    """根据名称获取 Feature Flag"""
    from app.memory.db import get_db

    conn = get_db()
    row = conn.execute(
        "SELECT * FROM feature_flags WHERE name = ?", (name,)
    ).fetchone()

    if row is None:
        return None

    return FeatureFlagResponse(
        id=row["id"],
        name=row["name"],
        description=row["description"],
        status=row["status"],
        enabled=bool(row["enabled"]),
        percentage=row["percentage"],
        conditions=json.loads(row["conditions"]) if row["conditions"] else None,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def list_flags(status: Optional[str] = None) -> list[FeatureFlagResponse]:
    """列出所有 Feature Flags"""
    from app.memory.db import get_db

    conn = get_db()
    if status:
        rows = conn.execute(
            "SELECT * FROM feature_flags WHERE status = ? ORDER BY created_at DESC",
            (status,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM feature_flags ORDER BY created_at DESC"
        ).fetchall()

    return [
        FeatureFlagResponse(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            status=row["status"],
            enabled=bool(row["enabled"]),
            percentage=row["percentage"],
            conditions=json.loads(row["conditions"]) if row["conditions"] else None,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
        for row in rows
    ]


def update_flag(name: str, update: FeatureFlagUpdate) -> Optional[FeatureFlagResponse]:
    """更新 Feature Flag"""
    from app.memory.db import get_db

    conn = get_db()
    now = datetime.now(timezone.utc).isoformat()

    # 构建更新字段
    updates = []
    params = []

    if update.description is not None:
        updates.append("description = ?")
        params.append(update.description)

    if update.status is not None:
        updates.append("status = ?")
        params.append(update.status.value)

    if update.enabled is not None:
        updates.append("enabled = ?")
        params.append(update.enabled)

    if update.percentage is not None:
        updates.append("percentage = ?")
        params.append(update.percentage)

    if update.conditions is not None:
        updates.append("conditions = ?")
        params.append(json.dumps(update.conditions))

    updates.append("updated_at = ?")
    params.append(now)

    params.append(name)

    conn.execute(
        f"UPDATE feature_flags SET {', '.join(updates)} WHERE name = ?",
        params,
    )
    conn.commit()

    return get_flag_by_name(name)


def delete_flag(name: str) -> bool:
    """删除 Feature Flag"""
    from app.memory.db import get_db

    conn = get_db()
    cursor = conn.execute("DELETE FROM feature_flags WHERE name = ?", (name,))
    conn.commit()

    return cursor.rowcount > 0


def evaluate_flag(name: str, user_id: Optional[str] = None, workspace_id: Optional[str] = None) -> bool:
    """评估 Feature Flag 是否启用"""
    from app.memory.db import get_db

    flag = get_flag_by_name(name)
    if flag is None or flag.status != FlagStatus.ACTIVE.value:
        return False

    if not flag.enabled:
        return False

    # 基于百分比的灰度
    if flag.percentage < 100:
        # 使用用户 ID 或 workspace ID 作为哈希种子
        seed = user_id or workspace_id or name
        hash_value = int(hashlib.md5(seed.encode()).hexdigest(), 16) % 100
        if hash_value >= flag.percentage:
            return False

    return True
