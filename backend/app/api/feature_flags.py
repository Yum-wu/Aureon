"""Feature Flags API — 功能开关 CRUD + 评估 (PostgreSQL asyncpg)."""

import json
from datetime import datetime, timezone
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.security.rbac import UserRole, require_role

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/feature-flags", tags=["feature-flags"])


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


async def _get_pool():
    from app.database.connection import get_db_pool
    pool = get_db_pool()
    if pool is None:
        raise RuntimeError("DATABASE_URL not configured — cannot access feature flags")
    return pool


async def _ensure_table():
    """Ensure table exists (PostgreSQL — schema.sql creates it, this is a safety net)."""
    pool = await _get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS feature_flags (
                id BIGSERIAL PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                description TEXT,
                status TEXT NOT NULL DEFAULT 'active',
                enabled BOOLEAN NOT NULL DEFAULT FALSE,
                percentage INTEGER NOT NULL DEFAULT 0,
                conditions TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)


def _row_to_flag(row) -> FeatureFlagOut:
    return FeatureFlagOut(
        id=row["id"],
        name=row["name"],
        description=row["description"],
        status=row["status"],
        enabled=bool(row["enabled"]),
        percentage=row["percentage"],
        conditions=json.loads(row["conditions"]) if row["conditions"] else None,
        created_at=row["created_at"].isoformat() if hasattr(row["created_at"], "isoformat") else row["created_at"],
        updated_at=row["updated_at"].isoformat() if hasattr(row["updated_at"], "isoformat") else row["updated_at"],
    )


@router.get("", response_model=list[FeatureFlagOut])
@router.get("/", response_model=list[FeatureFlagOut])
async def list_flags(status: Optional[str] = Query(None), _=Depends(require_role(UserRole.ADMIN))):
    pool = await _get_pool()
    async with pool.acquire() as conn:
        if status:
            rows = await conn.fetch("SELECT * FROM feature_flags WHERE status = $1 ORDER BY name", status)
        else:
            rows = await conn.fetch("SELECT * FROM feature_flags ORDER BY name")
    return [_row_to_flag(r) for r in rows]


@router.get("/{name}", response_model=FeatureFlagOut)
async def get_flag(name: str, _=Depends(require_role(UserRole.ADMIN))):
    pool = await _get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM feature_flags WHERE name = $1", name)
    if not row:
        from app.exceptions import NotFoundError
        raise NotFoundError(f"Feature flag '{name}' not found")
    return _row_to_flag(row)


@router.post("/{name}/toggle", response_model=FeatureFlagOut)
async def toggle_flag(name: str, _=Depends(require_role(UserRole.ADMIN))):
    pool = await _get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM feature_flags WHERE name = $1", name)
        if not row:
            from app.exceptions import NotFoundError
            raise NotFoundError(f"Feature flag '{name}' not found")
        now = datetime.now(timezone.utc)
        new_val = not row["enabled"]
        await conn.execute(
            "UPDATE feature_flags SET enabled = $1, updated_at = $2 WHERE name = $3",
            new_val, now, name,
        )
        row = await conn.fetchrow("SELECT * FROM feature_flags WHERE name = $1", name)
    return _row_to_flag(row)


@router.post("", response_model=FeatureFlagOut, status_code=201)
@router.post("/", response_model=FeatureFlagOut, status_code=201)
async def create_flag(flag: FeatureFlagCreate, _=Depends(require_role(UserRole.ADMIN))):
    pool = await _get_pool()
    now = datetime.now(timezone.utc)
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """INSERT INTO feature_flags (name, description, status, enabled, percentage, conditions, created_at, updated_at)
                   VALUES ($1, $2, 'active', $3, $4, $5, $6, $7)
                   RETURNING *""",
                flag.name,
                flag.description,
                flag.enabled,
                flag.percentage,
                json.dumps(flag.conditions, ensure_ascii=False) if flag.conditions else None,
                now, now,
            )
    except Exception as exc:
        from app.exceptions import ConflictError
        raise ConflictError(f"Flag '{flag.name}' already exists or conflict: {exc}")
    return _row_to_flag(row)


@router.put("/{name}", response_model=FeatureFlagOut)
async def update_flag(name: str, update: FeatureFlagUpdate, _=Depends(require_role(UserRole.ADMIN))):
    pool = await _get_pool()
    now = datetime.now(timezone.utc)
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM feature_flags WHERE name = $1", name)
        if not row:
            from app.exceptions import NotFoundError
            raise NotFoundError(f"Feature flag '{name}' not found")

        fields = {}
        if update.description is not None:
            fields["description"] = update.description
        if update.status is not None:
            fields["status"] = update.status
        if update.enabled is not None:
            fields["enabled"] = update.enabled
        if update.percentage is not None:
            fields["percentage"] = update.percentage
        if update.conditions is not None:
            fields["conditions"] = json.dumps(update.conditions, ensure_ascii=False)
        fields["updated_at"] = now

        if fields:
            set_clause = ", ".join(f"{k} = ${i+1}" for i, k in enumerate(fields))
            values = list(fields.values()) + [name]
            await conn.execute(
                f"UPDATE feature_flags SET {set_clause} WHERE name = ${len(fields)+1}",
                *values,
            )

        row = await conn.fetchrow("SELECT * FROM feature_flags WHERE name = $1", name)
    return _row_to_flag(row)


@router.delete("/{name}", status_code=204)
async def delete_flag(name: str, _=Depends(require_role(UserRole.ADMIN))):
    pool = await _get_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM feature_flags WHERE name = $1", name)


@router.get("/evaluate/{name}")
async def evaluate_flag(
    name: str,
    user_id: Optional[str] = Query(None),
    workspace_id: Optional[str] = Query(None),
):
    pool = await _get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM feature_flags WHERE name = $1 AND status = 'active'", name
        )
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
