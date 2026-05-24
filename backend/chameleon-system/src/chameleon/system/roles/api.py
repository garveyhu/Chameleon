"""roles HTTP 路由

挂点：/v1/admin/roles/*
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from chameleon.core.api.exceptions import (
    BusinessError,
    ResultCode,
    ValidationError,
)
from chameleon.core.api.response import Result
from chameleon.core.infra.db import get_session
from chameleon.core.models import Permission, Role, RolePermission
from chameleon.system.audit_logs import write_audit_log
from chameleon.system.audit_logs.context import AuditContext, get_audit_context
from chameleon.system.auth.dependencies import require_permission

# ── DTO ────────────────────────────────────────────────────


class RoleItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    description: str | None = None
    is_system: bool
    permission_codes: list[str] = Field(default_factory=list)


class CreateRoleRequest(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    description: str | None = None


class UpdateRoleRequest(BaseModel):
    name: str | None = None
    description: str | None = None


class SyncPermissionsRequest(BaseModel):
    permission_codes: list[str]


# ── helpers ────────────────────────────────────────────────


def _role_to_item(role: Role) -> RoleItem:
    return RoleItem(
        id=role.id,
        code=role.code,
        name=role.name,
        description=role.description,
        is_system=role.is_system,
        permission_codes=[p.code for p in (role.permissions or [])],
    )


# ── 路由 ───────────────────────────────────────────────────


router = APIRouter(prefix="/v1/admin/roles", tags=["admin:roles"])


@router.get("", response_model=Result[list[RoleItem]])
async def list_roles(
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("roles:read")),
) -> Result[list[RoleItem]]:
    rows = (
        (
            await session.execute(
                select(Role).options(selectinload(Role.permissions))
            )
        )
        .scalars()
        .all()
    )
    return Result.ok([_role_to_item(r) for r in rows])


@router.post("", response_model=Result[RoleItem])
async def create_role(
    req: CreateRoleRequest,
    session: AsyncSession = Depends(get_session),
    audit: AuditContext = Depends(get_audit_context),
    _: object = Depends(require_permission("roles:write")),
) -> Result[RoleItem]:
    existing = (
        await session.execute(select(Role).where(Role.code == req.code))
    ).scalar_one_or_none()
    if existing is not None:
        raise ValidationError(message=f"role code 已存在: {req.code}")
    role = Role(
        code=req.code, name=req.name, description=req.description, is_system=False
    )
    session.add(role)
    await session.flush()
    await write_audit_log(
        session,
        actor_user_id=audit.actor_user_id,
        actor_username=audit.actor_username,
        action="role.create",
        resource_type="role",
        resource_id=role.id,
        after={"code": role.code, "name": role.name},
        ip=audit.ip,
        user_agent=audit.user_agent,
        request_id=audit.request_id,
    )
    return Result.ok(_role_to_item(role))


@router.post("/{role_id}/update", response_model=Result[RoleItem])
async def update_role(
    role_id: int,
    req: UpdateRoleRequest,
    session: AsyncSession = Depends(get_session),
    audit: AuditContext = Depends(get_audit_context),
    _: object = Depends(require_permission("roles:write")),
) -> Result[RoleItem]:
    role = (
        await session.execute(
            select(Role)
            .where(Role.id == role_id)
            .options(selectinload(Role.permissions))
        )
    ).scalar_one_or_none()
    if role is None:
        raise BusinessError(ResultCode.AgentNotFound, message=f"role 不存在: {role_id}")
    before = {"name": role.name, "description": role.description}
    if req.name is not None:
        role.name = req.name
    if req.description is not None:
        role.description = req.description
    await session.flush()
    await write_audit_log(
        session,
        actor_user_id=audit.actor_user_id,
        actor_username=audit.actor_username,
        action="role.update",
        resource_type="role",
        resource_id=role.id,
        before=before,
        after={"name": role.name, "description": role.description},
        ip=audit.ip,
        user_agent=audit.user_agent,
        request_id=audit.request_id,
    )
    return Result.ok(_role_to_item(role))


@router.post("/{role_id}/delete", response_model=Result[None])
async def delete_role(
    role_id: int,
    session: AsyncSession = Depends(get_session),
    audit: AuditContext = Depends(get_audit_context),
    _: object = Depends(require_permission("roles:delete")),
) -> Result[None]:
    role = (
        await session.execute(select(Role).where(Role.id == role_id))
    ).scalar_one_or_none()
    if role is None:
        raise BusinessError(ResultCode.AgentNotFound, message=f"role 不存在: {role_id}")
    if role.is_system:
        raise ValidationError(message="内置角色不可删除")
    before = {"code": role.code, "name": role.name}
    # 级联清 role_permissions / user_roles 由 ondelete=CASCADE 处理
    await session.execute(delete(Role).where(Role.id == role_id))
    await session.flush()
    await write_audit_log(
        session,
        actor_user_id=audit.actor_user_id,
        actor_username=audit.actor_username,
        action="role.delete",
        resource_type="role",
        resource_id=role_id,
        before=before,
        ip=audit.ip,
        user_agent=audit.user_agent,
        request_id=audit.request_id,
    )
    return Result.ok(None)


@router.post("/{role_id}/permissions/sync", response_model=Result[RoleItem])
async def sync_permissions(
    role_id: int,
    req: SyncPermissionsRequest,
    session: AsyncSession = Depends(get_session),
    audit: AuditContext = Depends(get_audit_context),
    _: object = Depends(require_permission("roles:write")),
) -> Result[RoleItem]:
    role = (
        await session.execute(select(Role).where(Role.id == role_id))
    ).scalar_one_or_none()
    if role is None:
        raise BusinessError(ResultCode.AgentNotFound, message=f"role 不存在: {role_id}")

    # 校验全部 permission code 存在
    perm_ids = dict(
        (
            await session.execute(
                select(Permission.code, Permission.id).where(
                    Permission.code.in_(req.permission_codes)
                )
            )
        ).all()
    )
    missing = set(req.permission_codes) - set(perm_ids)
    if missing:
        raise ValidationError(message=f"未知 permission: {sorted(missing)}")

    # 清旧 + 加新
    await session.execute(
        RolePermission.__table__.delete().where(RolePermission.role_id == role_id)
    )
    for pid in perm_ids.values():
        session.add(RolePermission(role_id=role_id, permission_id=pid))
    await session.flush()
    await write_audit_log(
        session,
        actor_user_id=audit.actor_user_id,
        actor_username=audit.actor_username,
        action="role_permission.sync",
        resource_type="role_permission",
        resource_id=role_id,
        after={"permission_codes": req.permission_codes},
        ip=audit.ip,
        user_agent=audit.user_agent,
        request_id=audit.request_id,
    )

    # 重读返回
    role = (
        await session.execute(
            select(Role)
            .where(Role.id == role_id)
            .options(selectinload(Role.permissions))
        )
    ).scalar_one()
    return Result.ok(_role_to_item(role))
