"""用户管理 API Router

提供用户 CRUD、邀请、密码重置等端点。
所有端点需要 ADMIN 角色，支持租户隔离。
用户数据存储在 SQLite（复用 memory/db.py）。
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


# ── SQLite 存储层 ──

def _init_users_table() -> None:
    """初始化用户表（幂等）。"""
    from app.memory.db import get_db
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            email TEXT NOT NULL,
            display_name TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'viewer',
            status TEXT NOT NULL DEFAULT 'active',
            tenant_id TEXT NOT NULL DEFAULT 'default',
            workspace_ids TEXT DEFAULT '[]',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_users_tenant ON users(tenant_id)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_users_email ON users(email, tenant_id)
    """)
    conn.commit()


def _row_to_user(row: dict) -> User:
    """将 SQLite Row 转换为 User 模型。"""
    import json as _json
    workspace_ids = []
    raw_ws = row.get("workspace_ids", "[]")
    if raw_ws:
        try:
            workspace_ids = _json.loads(raw_ws) if isinstance(raw_ws, str) else raw_ws
        except (_json.JSONDecodeError, TypeError):
            workspace_ids = []

    return User(
        id=row["id"],
        email=row["email"],
        display_name=row["display_name"],
        role=row["role"],
        status=row["status"],
        tenant_id=row["tenant_id"],
        workspace_ids=workspace_ids,
        created_at=row.get("created_at", ""),
        last_login=row.get("last_login"),
    )


# ── 端点 ──

@router.get("", response_model=UserListResponse)
async def list_users(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    role: Optional[str] = Query(None, pattern=r"^(viewer|editor|admin)$", description="角色过滤"),
    status: Optional[str] = Query(None, pattern=r"^(active|suspended|invited)$", description="状态过滤"),
    user: dict = Depends(require_role(UserRole.ADMIN)),
):
    """获取用户列表（需 ADMIN 角色）

    支持分页和按角色/状态过滤，仅返回当前租户用户。
    """
    _init_users_table()
    tenant_id = get_current_tenant_id()

    from app.memory.db import get_db
    conn = get_db()

    # 构建查询条件
    conditions = ["tenant_id = ?"]
    params: list = [tenant_id]

    if role:
        conditions.append("role = ?")
        params.append(role)
    if status:
        conditions.append("status = ?")
        params.append(status)

    where_clause = " AND ".join(conditions)

    # 总数
    total_row = conn.execute(
        f"SELECT COUNT(*) as cnt FROM users WHERE {where_clause}",
        params,
    ).fetchone()
    total = total_row["cnt"] if total_row else 0

    # 分页查询
    offset = (page - 1) * page_size
    rows = conn.execute(
        f"SELECT * FROM users WHERE {where_clause} ORDER BY created_at DESC LIMIT ? OFFSET ?",
        params + [page_size, offset],
    ).fetchall()

    users = [_row_to_user(dict(row)) for row in rows]

    return UserListResponse(users=users, total=total, page=page, page_size=page_size)


@router.post("", response_model=User, status_code=201)
async def invite_user(
    req: UserCreate,
    user: dict = Depends(require_role(UserRole.ADMIN)),
):
    """邀请用户（需 ADMIN 角色）

    创建新用户记录，状态为 invited。
    """
    _init_users_table()
    tenant_id = get_current_tenant_id()

    from app.memory.db import get_db
    import json as _json

    conn = get_db()
    user_id = str(uuid.uuid4())
    display_name = req.display_name or req.email.split("@")[0]
    now = datetime.now(timezone.utc).isoformat()

    try:
        conn.execute(
            """
            INSERT INTO users (id, email, display_name, role, status, tenant_id, workspace_ids, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                req.email,
                display_name,
                req.role,
                "invited",
                tenant_id,
                _json.dumps(req.workspace_ids),
                now,
            ),
        )
        conn.commit()
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
        created_at=now,
        last_login=None,
    )


@router.get("/{user_id}", response_model=User)
async def get_user(
    user_id: str,
    user: dict = Depends(require_role(UserRole.ADMIN)),
):
    """获取用户详情（需 ADMIN 角色）"""
    _init_users_table()
    tenant_id = get_current_tenant_id()

    from app.memory.db import get_db
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM users WHERE id = ? AND tenant_id = ?",
        (user_id, tenant_id),
    ).fetchone()

    if row is None:
        raise NotFoundError("User not found")

    return _row_to_user(dict(row))


@router.put("/{user_id}", response_model=User)
async def update_user(
    user_id: str,
    req: UserUpdate,
    user: dict = Depends(require_role(UserRole.ADMIN)),
):
    """更新用户信息（需 ADMIN 角色）

    支持修改角色、状态、显示名称和所属 Workspace。
    """
    _init_users_table()
    tenant_id = get_current_tenant_id()

    from app.memory.db import get_db
    import json as _json

    conn = get_db()

    # 验证用户存在且属于当前租户
    existing = conn.execute(
        "SELECT * FROM users WHERE id = ? AND tenant_id = ?",
        (user_id, tenant_id),
    ).fetchone()
    if existing is None:
        raise NotFoundError("User not found")

    # 构建更新字段
    updates: list[str] = []
    params: list = []

    if req.role is not None:
        updates.append("role = ?")
        params.append(req.role)
    if req.status is not None:
        updates.append("status = ?")
        params.append(req.status)
    if req.display_name is not None:
        updates.append("display_name = ?")
        params.append(req.display_name)
    if req.workspace_ids is not None:
        updates.append("workspace_ids = ?")
        params.append(_json.dumps(req.workspace_ids))

    if not updates:
        return _row_to_user(dict(existing))

    params.append(user_id)
    params.append(tenant_id)
    conn.execute(
        f"UPDATE users SET {', '.join(updates)} WHERE id = ? AND tenant_id = ?",
        params,
    )
    conn.commit()

    # 重新读取
    row = conn.execute(
        "SELECT * FROM users WHERE id = ? AND tenant_id = ?",
        (user_id, tenant_id),
    ).fetchone()
    return _row_to_user(dict(row))


@router.delete("/{user_id}", status_code=204)
async def delete_user(
    user_id: str,
    user: dict = Depends(require_role(UserRole.ADMIN)),
):
    """软删除用户（需 ADMIN 角色）

    将用户状态设为 suspended，而非物理删除。
    """
    _init_users_table()
    tenant_id = get_current_tenant_id()

    from app.memory.db import get_db
    conn = get_db()

    existing = conn.execute(
        "SELECT * FROM users WHERE id = ? AND tenant_id = ?",
        (user_id, tenant_id),
    ).fetchone()
    if existing is None:
        raise NotFoundError("User not found")

    conn.execute(
        "UPDATE users SET status = 'suspended' WHERE id = ? AND tenant_id = ?",
        (user_id, tenant_id),
    )
    conn.commit()


@router.post("/{user_id}/reset-password")
async def reset_password(
    user_id: str,
    user: dict = Depends(require_role(UserRole.ADMIN)),
):
    """重置用户密码（需 ADMIN 角色）

    生成密码重置令牌（当前为占位实现，返回成功状态）。
    """
    _init_users_table()
    tenant_id = get_current_tenant_id()

    from app.memory.db import get_db
    conn = get_db()

    existing = conn.execute(
        "SELECT * FROM users WHERE id = ? AND tenant_id = ?",
        (user_id, tenant_id),
    ).fetchone()
    if existing is None:
        raise NotFoundError("User not found")

    # 占位：生产环境应发送重置邮件或生成一次性令牌
    logger.info("password_reset_requested", user_id=user_id, tenant_id=tenant_id)
    return {"status": "reset_requested", "user_id": user_id}
