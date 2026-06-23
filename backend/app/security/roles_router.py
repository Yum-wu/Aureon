"""角色与权限管理 API Router

提供角色列表、权限列表和角色权限更新端点。
所有端点需要 ADMIN 角色。
"""

from typing import Dict, List

import structlog
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.security.rbac import UserRole, Permission, ROLE_PERMISSIONS, require_role

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/security/roles", tags=["roles"])


# ── 数据模型 ──

class Role(BaseModel):
    """角色模型。"""
    name: str = Field(..., description="角色标识: viewer/editor/admin")
    display_name: str = Field(..., description="显示名称")
    permissions: List[str] = Field(..., description="权限列表")
    description: str = Field(..., description="角色描述")


class RoleUpdate(BaseModel):
    """角色权限更新请求。"""
    permissions: List[str] = Field(..., description="新的权限列表")


# ── 角色元数据 ──

_ROLE_META: Dict[str, Dict[str, str]] = {
    "VIEWER": {
        "display_name": "查看者",
        "description": "可查看知识库内容，无法上传或修改",
    },
    "EDITOR": {
        "display_name": "编辑者",
        "description": "可查看、上传和编辑知识库内容",
    },
    "ADMIN": {
        "display_name": "管理员",
        "description": "拥有所有权限，包括用户管理、系统配置和审计",
    },
}


# ── 端点 ──

@router.get("", response_model=List[Role])
async def list_roles(
    user: dict = Depends(require_role(UserRole.ADMIN)),
):
    """获取所有角色及其权限（需 ADMIN 角色）"""
    result: List[Role] = []
    for role_enum, perms in ROLE_PERMISSIONS.items():
        meta = _ROLE_META.get(role_enum.name, {})
        result.append(Role(
            name=role_enum.name.lower(),
            display_name=meta.get("display_name", role_enum.name),
            permissions=[p.value for p in perms],
            description=meta.get("description", ""),
        ))
    return result


@router.get("/permissions", response_model=List[dict])
async def list_permissions(
    user: dict = Depends(require_role(UserRole.ADMIN)),
):
    """获取所有可用权限（需 ADMIN 角色）"""
    return [
        {"name": p.value, "description": _PERMISSION_DESCRIPTIONS.get(p.value, "")}
        for p in Permission
    ]


@router.put("/{role_name}")
async def update_role_permissions(
    role_name: str,
    req: RoleUpdate,
    user: dict = Depends(require_role(UserRole.ADMIN)),
):
    """更新角色权限（需 ADMIN 角色）

    注意：此端点修改运行时内存中的权限映射，
    不持久化（服务重启后恢复默认）。
    生产环境应配合数据库或配置中心持久化。
    """
    # 验证角色名有效
    try:
        role_enum = UserRole[role_name.upper()]
    except KeyError:
        from app.exceptions import NotFoundError
        raise NotFoundError(f"Role '{role_name}' not found")

    # 验证权限名有效
    new_perms: set[Permission] = set()
    valid_names = {p.value for p in Permission}
    for perm_name in req.permissions:
        if perm_name not in valid_names:
            from app.exceptions import AureonException
            raise AureonException(
                status_code=400,
                detail=f"Invalid permission: {perm_name}. Valid: {sorted(valid_names)}",
            )
        new_perms.add(Permission(perm_name))

    # Enforce: cannot grant permissions beyond your own role level
    requesting_role = user.get("_role", UserRole.VIEWER)
    if role_enum.value > requesting_role.value:
        from app.exceptions import AuthorizationError
        raise AuthorizationError("Cannot modify permissions of a role higher than your own")

    # Enforce: cannot grant permissions you don't have
    requesting_perms = ROLE_PERMISSIONS.get(requesting_role, set())
    excessive_perms = new_perms - requesting_perms
    if excessive_perms:
        from app.exceptions import AuthorizationError
        raise AuthorizationError(
            f"Cannot grant permissions you don't have: {[p.value for p in excessive_perms]}"
        )

    # 更新运行时权限映射
    ROLE_PERMISSIONS[role_enum] = new_perms
    logger.info(
        "role_permissions_updated",
        role=role_name,
        permissions=[p.value for p in new_perms],
        updated_by=user.get("sub", "unknown"),
    )

    meta = _ROLE_META.get(role_enum.name, {})
    return Role(
        name=role_enum.name.lower(),
        display_name=meta.get("display_name", role_enum.name),
        permissions=[p.value for p in new_perms],
        description=meta.get("description", ""),
    )


# ── 权限描述 ──

_PERMISSION_DESCRIPTIONS: Dict[str, str] = {
    "read": "查看知识库内容和查询结果",
    "write": "编辑知识库内容",
    "upload": "上传文档到知识库",
    "index": "管理索引（创建、重建、删除）",
    "admin": "系统管理（用户、配置、审计）",
}
