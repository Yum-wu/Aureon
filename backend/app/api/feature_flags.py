"""Feature Flags API — 功能开关 CRUD + 评估"""

import json
from datetime import datetime, timezone
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.memory.db import get_db
from app.security.rbac import UserRole, require_role

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/feature-flags", tags=["feature-flags"])


class FeatureFlagOut(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    status: str = "active"
    enabled: bool = False
    percentage: int = 0
    conditions: Optional[dict] = None
    created_at: str
    updated_at: str


class FeatureFlagCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    description: Optional[str] = None
    enabled: bool = False
    percentage: int = Field(default=0, ge=0, le=100)
    conditions: Optional[dict] = None


class FeatureFlagUpdate(BaseModel):
    description: Optional[str] = None
    status: Optional[str] = None
    enabled: Optional[bool] = None
    percentage: Optional[int] = Field(default=None, ge=0, le=100)
    conditions: Optional[dict] = None


def _init_table():
    db = get_db()
    db.executescript("""
        CREATE TABLE IF NOT EXISTS feature_flags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            description TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            enabled INTEGER NOT NULL DEFAULT 0,
            percentage INTEGER NOT NULL DEFAULT 0,
            conditions TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_ff_name ON feature_flags(name);
    """)
    db.commit()


def _row_to_flag(row) -> FeatureFlagOut:
    return FeatureFlagOut(
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


@router.get("", response_model=list[FeatureFlagOut])
@router.get("/", response_model=list[FeatureFlagOut])
async def list_flags(status: Optional[str] = Query(None), _=Depends(require_role(UserRole.ADMIN))):
    _init_table()
    db = get_db()
    if status:
        rows = db.execute("SELECT * FROM feature_flags WHERE status = ? ORDER BY name", (status,)).fetchall()
    else:
        rows = db.execute("SELECT * FROM feature_flags ORDER BY name").fetchall()
    return [_row_to_flag(r) for r in rows]


@router.get("/{name}", response_model=FeatureFlagOut)
async def get_flag(name: str, _=Depends(require_role(UserRole.ADMIN))):
    _init_table()
    db = get_db()
    row = db.execute("SELECT * FROM feature_flags WHERE name = ?", (name,)).fetchone()
    if not row:
        from app.exceptions import NotFoundError
        raise NotFoundError(f"Feature flag '{name}' not found")
    return _row_to_flag(row)


@router.post("", response_model=FeatureFlagOut, status_code=201)
@router.post("/", response_model=FeatureFlagOut, status_code=201)
async def create_flag(flag: FeatureFlagCreate, _=Depends(require_role(UserRole.ADMIN))):
    _init_table()
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()
    try:
        db.execute(
            """INSERT INTO feature_flags (name, description, status, enabled, percentage, conditions, created_at, updated_at)
               VALUES (?, ?, 'active', ?, ?, ?, ?, ?)""",
            (flag.name, flag.description, int(flag.enabled), flag.percentage,
             json.dumps(flag.conditions, ensure_ascii=False) if flag.conditions else None,
             now, now),
        )
        db.commit()
    except Exception as exc:
        from app.exceptions import ConflictError
        raise ConflictError(f"Flag '{flag.name}' already exists or conflict: {exc}")
    row = db.execute("SELECT * FROM feature_flags WHERE name = ?", (flag.name,)).fetchone()
    return _row_to_flag(row)


@router.put("/{name}", response_model=FeatureFlagOut)
async def update_flag(name: str, update: FeatureFlagUpdate, _=Depends(require_role(UserRole.ADMIN))):
    _init_table()
    db = get_db()
    row = db.execute("SELECT * FROM feature_flags WHERE name = ?", (name,)).fetchone()
    if not row:
        from app.exceptions import NotFoundError
        raise NotFoundError(f"Feature flag '{name}' not found")
    now = datetime.now(timezone.utc).isoformat()
    fields = {}
    if update.description is not None:
        fields["description"] = update.description
    if update.status is not None:
        fields["status"] = update.status
    if update.enabled is not None:
        fields["enabled"] = int(update.enabled)
    if update.percentage is not None:
        fields["percentage"] = update.percentage
    if update.conditions is not None:
        fields["conditions"] = json.dumps(update.conditions, ensure_ascii=False)
    fields["updated_at"] = now
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    db.execute(f"UPDATE feature_flags SET {set_clause} WHERE name = ?", (*fields.values(), name))
    db.commit()
    row = db.execute("SELECT * FROM feature_flags WHERE name = ?", (name,)).fetchone()
    return _row_to_flag(row)


@router.delete("/{name}", status_code=204)
async def delete_flag(name: str, _=Depends(require_role(UserRole.ADMIN))):
    _init_table()
    db = get_db()
    db.execute("DELETE FROM feature_flags WHERE name = ?", (name,))
    db.commit()


@router.get("/evaluate/{name}")
async def evaluate_flag(
    name: str,
    user_id: Optional[str] = Query(None),
    workspace_id: Optional[str] = Query(None),
):
    _init_table()
    db = get_db()
    row = db.execute("SELECT * FROM feature_flags WHERE name = ? AND status = 'active'", (name,)).fetchone()
    if not row:
        return {"enabled": False}
    if row["enabled"]:
        return {"enabled": True}
    # percentage-based rollout
    import hashlib
    key = user_id or workspace_id or "anonymous"
    hash_val = int(hashlib.sha256(key.encode()).hexdigest(), 16) % 100
    if hash_val < row["percentage"]:
        return {"enabled": True}
    return {"enabled": False}
