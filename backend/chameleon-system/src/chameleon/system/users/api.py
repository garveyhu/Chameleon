"""users HTTP 路由

挂点：/v1/admin/users/*
鉴权：require_permission("users:read"/"users:write"/"users:delete")
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.api.response import PageParams, PageResult, Result
from chameleon.data.infra.db import get_session
from chameleon.system.audit_logs import write_audit_log
from chameleon.system.audit_logs.context import AuditContext, get_audit_context
from chameleon.system.auth.dependencies import require_permission
from chameleon.system.users import service
from chameleon.system.users.schemas import (
    CreateUserRequest,
    GrantRoleRequest,
    ResetPasswordRequest,
    UpdateUserRequest,
    UserItem,
)

router = APIRouter(prefix="/v1/admin/users", tags=["admin:users"])


@router.get("", response_model=Result[PageResult[UserItem]])
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("users:read")),
) -> Result[PageResult[UserItem]]:
    return Result.ok(await service.list_users(session, PageParams(page=page, page_size=page_size)))


@router.get("/{user_id}", response_model=Result[UserItem])
async def get_user(
    user_id: int,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("users:read")),
) -> Result[UserItem]:
    return Result.ok(await service.get_user(session, user_id))


@router.post("", response_model=Result[UserItem])
async def create_user(
    req: CreateUserRequest,
    session: AsyncSession = Depends(get_session),
    audit: AuditContext = Depends(get_audit_context),
    _: object = Depends(require_permission("users:write")),
) -> Result[UserItem]:
    item = await service.create_user(session, req)
    await write_audit_log(
        session,
        actor_user_id=audit.actor_user_id,
        actor_username=audit.actor_username,
        action="user.create",
        resource_type="user",
        resource_id=item.id,
        after={"username": item.username, "roles": item.role_codes},
        ip=audit.ip,
        user_agent=audit.user_agent,
        request_id=audit.request_id,
    )
    return Result.ok(item)


@router.post("/{user_id}/update", response_model=Result[UserItem])
async def update_user(
    user_id: int,
    req: UpdateUserRequest,
    session: AsyncSession = Depends(get_session),
    audit: AuditContext = Depends(get_audit_context),
    _: object = Depends(require_permission("users:write")),
) -> Result[UserItem]:
    item = await service.update_user(session, user_id, req)
    await write_audit_log(
        session,
        actor_user_id=audit.actor_user_id,
        actor_username=audit.actor_username,
        action="user.update",
        resource_type="user",
        resource_id=item.id,
        after={"username": item.username, "status": item.status},
        ip=audit.ip,
        user_agent=audit.user_agent,
        request_id=audit.request_id,
    )
    return Result.ok(item)


@router.post("/{user_id}/delete", response_model=Result[None])
async def delete_user(
    user_id: int,
    session: AsyncSession = Depends(get_session),
    audit: AuditContext = Depends(get_audit_context),
    _: object = Depends(require_permission("users:delete")),
) -> Result[None]:
    await service.delete_user(session, user_id)
    await write_audit_log(
        session,
        actor_user_id=audit.actor_user_id,
        actor_username=audit.actor_username,
        action="user.delete",
        resource_type="user",
        resource_id=user_id,
        ip=audit.ip,
        user_agent=audit.user_agent,
        request_id=audit.request_id,
    )
    return Result.ok(None)


@router.post("/{user_id}/reset-password", response_model=Result[None])
async def reset_password(
    user_id: int,
    req: ResetPasswordRequest,
    session: AsyncSession = Depends(get_session),
    audit: AuditContext = Depends(get_audit_context),
    _: object = Depends(require_permission("users:write")),
) -> Result[None]:
    await service.reset_password(session, user_id, req)
    await write_audit_log(
        session,
        actor_user_id=audit.actor_user_id,
        actor_username=audit.actor_username,
        action="user.reset_password",
        resource_type="user",
        resource_id=user_id,
        ip=audit.ip,
        user_agent=audit.user_agent,
        request_id=audit.request_id,
    )
    return Result.ok(None)


@router.post("/{user_id}/roles/grant", response_model=Result[UserItem])
async def grant_role(
    user_id: int,
    req: GrantRoleRequest,
    session: AsyncSession = Depends(get_session),
    audit: AuditContext = Depends(get_audit_context),
    _: object = Depends(require_permission("users:write")),
) -> Result[UserItem]:
    item = await service.grant_role(session, user_id, req.role_code)
    await write_audit_log(
        session,
        actor_user_id=audit.actor_user_id,
        actor_username=audit.actor_username,
        action="user_role.grant",
        resource_type="user_role",
        resource_id=user_id,
        after={"role": req.role_code},
        ip=audit.ip,
        user_agent=audit.user_agent,
        request_id=audit.request_id,
    )
    return Result.ok(item)


@router.post("/{user_id}/roles/revoke", response_model=Result[UserItem])
async def revoke_role(
    user_id: int,
    req: GrantRoleRequest,
    session: AsyncSession = Depends(get_session),
    audit: AuditContext = Depends(get_audit_context),
    _: object = Depends(require_permission("users:write")),
) -> Result[UserItem]:
    item = await service.revoke_role(session, user_id, req.role_code)
    await write_audit_log(
        session,
        actor_user_id=audit.actor_user_id,
        actor_username=audit.actor_username,
        action="user_role.revoke",
        resource_type="user_role",
        resource_id=user_id,
        after={"role": req.role_code},
        ip=audit.ip,
        user_agent=audit.user_agent,
        request_id=audit.request_id,
    )
    return Result.ok(item)
