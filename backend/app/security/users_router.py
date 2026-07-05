"""用户管理 API Router

提供用户 CRUD、邀请、密码重置等端点。
所有端点需要 ADMIN 角色，支持租户隔离。
数据存储在 PostgreSQL（asyncpg）。
"""

import uuid
from datetime import datetime, timezone
from typing import List, Optional

import structlog
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, EmailStr, Field

from app.exceptions import NotFoundError
from app.security.rbac import UserRole, require_role
from app.multi_tenant.middleware import get_current_tenant_id

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/security/users", tags=["users"])


# ── 数据模型 ──

class User(BaseModel):
    """用户模型。"""
    id: str = Field(..., description="UUID")
    email: str = Field(..., description="邮箱地址")
    display_name: str = Field(..., description="显示名称")
    role: str = Field("viewer", description="角色: viewer/editor/admin")
    status: str = Field("active", description="状态: active/suspended/invited")
    tenant_id: str = Field(..., description="租户 ID")
    workspace_ids: List[str] = Field(default_factory=list, description="所属 Workspace 列表")
    created_at: str = Field(default="", description="创建时间")
    last_login: Optional[str] = Field(None, description="最后登录时间")


class UserCreate(BaseModel):
    """创建/邀请用户请求。"""
    email: EmailStr = Field(..., description="邮箱地址")
    role: str = Field("viewer", pattern=r"^(viewer|editor|admin)$", description="角色")
    display_name: Optional[str] = Field(None, description="显示名称（默认使用邮箱前缀）")
    workspace_ids: List[str] = Field(default_factory=list, description="所属 Workspace")


class UserUpdate(BaseModel):
    """更新用户请求。"""
    role: Optional[str] = Field(None, pattern=r"^(viewer|editor|admin)$", description="角色")
    status: Optional[str] = Field(None, pattern=r"^(active|suspended|invited)$", description="状态")
    display_name: Optional[str] = Field(None, description="显示名称")
    workspace_ids: Optional[List[str]] = Field(None, description="所属 Workspace")


class UserListResponse(BaseModel):
    """用户列表响应。"""
    users: List[User]
    total: int
    page: int
    page_size: int


# ── asyncpg 助手 ──


async def _get_pool():
    from app.database.connection import get_db_pool
    pool = get_db_pool()
    if pool is None:
        raise RuntimeError("DATABASE_URL not configured — cannot access users")
    return pool


def _row_to_user(row) -> User:
    """将 asyncpg Record 转换为 User 模型。"""
    import json as _json
    workspace_ids = []
    raw_ws = row.get("workspace_ids", "[]")
    if raw_ws:
        try:
            workspace_ids = _json.loads(raw_ws) if isinstance(raw_ws, str) else raw_ws
        except (_json.JSONDecodeError, TypeError):
            workspace_ids = []

    created_at = row.get("created_at", "")
    if hasattr(created_at, "isoformat"):
        created_at = created_at.isoformat()

    last_login = row.get("last_login")
    if hasattr(last_login, "isoformat"):
        last_login = last_login.isoformat()

    return User(
        id=row["id"],
        email=row["email"],
        display_name=row["display_name"],
        role=row["role"],
        status=row["status"],
        tenant_id=row["tenant_id"],
        workspace_ids=workspace_ids,
        created_at=created_at,
        last_login=last_login,
    )


def _row_to_user_dict(row) -> User:
    """Convert asyncpg Record to User, for pre-existing row."""
    return _row_to_user(row)


# ── 端点 ──


@router.get("", response_model=UserListResponse)
async def list_users(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    role: Optional[str] = Query(None, pattern=r"^(viewer|editor|admin)$", description="角色过滤"),
    status: Optional[str] = Query(None, pattern=r"^(active|suspended|invited)$", description="状态过滤"),
    user: dict = Depends(require_role(UserRole.ADMIN)),
):
    """获取用户列表（需 ADMIN 角色）"""
    pool = await _get_pool()
    tenant_id = get_current_tenant_id()

    conditions = ["tenant_id = $1"]
    params: list = [tenant_id]
    param_idx = 2

    if role:
        conditions.append(f"role = ${param_idx}")
        params.append(role)
        param_idx += 1
    if status:
        conditions.append(f"status = ${param_idx}")
        params.append(status)
        param_idx += 1

    where_clause = " AND ".join(conditions)

    async with pool.acquire() as conn:
        total_row = await conn.fetchrow(
            f"SELECT COUNT(*) as cnt FROM users WHERE {where_clause}",
            *params,
        )
        total = total_row["cnt"] if total_row else 0

        offset = (page - 1) * page_size
        rows = await conn.fetch(
            f"SELECT * FROM users WHERE {where_clause} ORDER BY created_at DESC LIMIT ${param_idx} OFFSET ${param_idx + 1}",
            *params, page_size, offset,
        )

    users = [_row_to_user(row) for row in rows]
    return UserListResponse(users=users, total=total, page=page, page_size=page_size)


@router.post("", response_model=User, status_code=201)
async def invite_user(
    req: UserCreate,
    user: dict = Depends(require_role(UserRole.ADMIN)),
):
    """邀请用户（需 ADMIN 角色）"""
    pool = await _get_pool()
    tenant_id = get_current_tenant_id()
    import json as _json

    user_id = str(uuid.uuid4())
    display_name = req.display_name or req.email.split("@")[0]
    now = datetime.now(timezone.utc)

    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO users (id, email, display_name, role, status, tenant_id, workspace_ids, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """,
                user_id, req.email, display_name, req.role, "invited", tenant_id,
                _json.dumps(req.workspace_ids), now,
            )
    except Exception as exc:
        logger.warning("user_invite_failed", email=req.email, error=str(exc))
        from app.exceptions import AureonException
        raise AureonException(status_code=409, detail=f"Failed to invite user: {exc}")

    return User(
        id=user_id,
        email=req.email,
        display_name=display_name,
        role=req.role,
        status="invited",
        tenant_id=tenant_id,
        workspace_ids=req.workspace_ids,
        created_at=now.isoformat(),
        last_login=None,
    )


@router.get("/{user_id}", response_model=User)
async def get_user(
    user_id: str,
    user: dict = Depends(require_role(UserRole.ADMIN)),
):
    """获取用户详情（需 ADMIN 角色）"""
    pool = await _get_pool()
    tenant_id = get_current_tenant_id()

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM users WHERE id = $1 AND tenant_id = $2",
            user_id, tenant_id,
        )

    if row is None:
        raise NotFoundError("User not found")

    return _row_to_user(row)


@router.put("/{user_id}", response_model=User)
async def update_user(
    user_id: str,
    req: UserUpdate,
    user: dict = Depends(require_role(UserRole.ADMIN)),
):
    """更新用户信息（需 ADMIN 角色）"""
    pool = await _get_pool()
    tenant_id = get_current_tenant_id()
    import json as _json

    async with pool.acquire() as conn:
        existing = await conn.fetchrow(
            "SELECT * FROM users WHERE id = $1 AND tenant_id = $2",
            user_id, tenant_id,
        )
        if existing is None:
            raise NotFoundError("User not found")

        updates: list[str] = []
        params: list = []
        param_idx = 1

        if req.role is not None:
            updates.append(f"role = ${param_idx}")
            params.append(req.role)
            param_idx += 1
        if req.status is not None:
            updates.append(f"status = ${param_idx}")
            params.append(req.status)
            param_idx += 1
        if req.display_name is not None:
            updates.append(f"display_name = ${param_idx}")
            params.append(req.display_name)
            param_idx += 1
        if req.workspace_ids is not None:
            updates.append(f"workspace_ids = ${param_idx}")
            params.append(_json.dumps(req.workspace_ids))
            param_idx += 1

        if not updates:
            return _row_to_user(existing)

        params.extend([user_id, tenant_id])
        await conn.execute(
            f"UPDATE users SET {', '.join(updates)} WHERE id = ${param_idx} AND tenant_id = ${param_idx + 1}",
            *params,
        )

        row = await conn.fetchrow(
            "SELECT * FROM users WHERE id = $1 AND tenant_id = $2",
            user_id, tenant_id,
        )
    return _row_to_user(row)


@router.delete("/{user_id}", status_code=204)
async def delete_user(
    user_id: str,
    user: dict = Depends(require_role(UserRole.ADMIN)),
):
    """软删除用户（需 ADMIN 角色）"""
    pool = await _get_pool()
    tenant_id = get_current_tenant_id()

    async with pool.acquire() as conn:
        existing = await conn.fetchrow(
            "SELECT * FROM users WHERE id = $1 AND tenant_id = $2",
            user_id, tenant_id,
        )
        if existing is None:
            raise NotFoundError("User not found")

        await conn.execute(
            "UPDATE users SET status = 'suspended' WHERE id = $1 AND tenant_id = $2",
            user_id, tenant_id,
        )


@router.post("/{user_id}/reset-password")
async def reset_password(
    user_id: str,
    user: dict = Depends(require_role(UserRole.ADMIN)),
):
    """重置用户密码（需 ADMIN 角色）"""
    pool = await _get_pool()
    tenant_id = get_current_tenant_id()

    async with pool.acquire() as conn:
        existing = await conn.fetchrow(
            "SELECT * FROM users WHERE id = $1 AND tenant_id = $2",
            user_id, tenant_id,
        )
        if existing is None:
            raise NotFoundError("User not found")

    logger.info("password_reset_requested", user_id=user_id, tenant_id=tenant_id)
    return {"status": "reset_requested", "user_id": user_id}
