"""workspaces HTTP 路由（/v1/admin/workspaces）"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.api.response import Result
from chameleon.core.infra.db import get_session
from chameleon.system.audit_logs import write_audit_log
from chameleon.system.audit_logs.context import AuditContext, get_audit_context
from chameleon.system.auth.dependencies import require_permission
from chameleon.system.workspaces import service
from chameleon.system.workspaces.schemas import (
    AddMemberRequest,
    CreateWorkspaceRequest,
    MemberItem,
    QuotaItem,
    UpdateMemberRoleRequest,
    UpdateQuotaRequest,
    UpdateWorkspaceRequest,
    WorkspaceItem,
)

router = APIRouter(prefix="/v1/admin/workspaces", tags=["admin:workspaces"])

_PERM_READ = "workspaces:read"
_PERM_WRITE = "workspaces:write"
_PERM_DELETE = "workspaces:delete"


# ── workspace CRUD ─────────────────────────────────────


@router.get("", response_model=Result[list[WorkspaceItem]])
async def list_workspaces(
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission(_PERM_READ)),
) -> Result[list[WorkspaceItem]]:
    return Result.ok(await service.list_workspaces(session))


@router.get("/{ws_id}", response_model=Result[WorkspaceItem])
async def get_workspace(
    ws_id: int,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission(_PERM_READ)),
) -> Result[WorkspaceItem]:
    return Result.ok(await service.get_workspace(session, ws_id))


@router.post("", response_model=Result[WorkspaceItem])
async def create_workspace(
    req: CreateWorkspaceRequest,
    session: AsyncSession = Depends(get_session),
    audit: AuditContext = Depends(get_audit_context),
    _: object = Depends(require_permission(_PERM_WRITE)),
) -> Result[WorkspaceItem]:
    item = await service.create_workspace(session, req)
    await write_audit_log(
        session,
        actor_user_id=audit.actor_user_id,
        actor_username=audit.actor_username,
        action="workspace.create",
        resource_type="workspace",
        resource_id=item.id,
        after={"workspace_key": item.workspace_key, "name": item.name, "plan": item.plan},
        ip=audit.ip,
        user_agent=audit.user_agent,
        request_id=audit.request_id,
    )
    return Result.ok(item)


@router.post("/{ws_id}/update", response_model=Result[WorkspaceItem])
async def update_workspace(
    ws_id: int,
    req: UpdateWorkspaceRequest,
    session: AsyncSession = Depends(get_session),
    audit: AuditContext = Depends(get_audit_context),
    _: object = Depends(require_permission(_PERM_WRITE)),
) -> Result[WorkspaceItem]:
    item = await service.update_workspace(session, ws_id, req)
    await write_audit_log(
        session,
        actor_user_id=audit.actor_user_id,
        actor_username=audit.actor_username,
        action="workspace.update",
        resource_type="workspace",
        resource_id=item.id,
        after={"name": item.name, "plan": item.plan},
        ip=audit.ip,
        user_agent=audit.user_agent,
        request_id=audit.request_id,
    )
    return Result.ok(item)


@router.post("/{ws_id}/delete", response_model=Result[None])
async def delete_workspace(
    ws_id: int,
    session: AsyncSession = Depends(get_session),
    audit: AuditContext = Depends(get_audit_context),
    _: object = Depends(require_permission(_PERM_DELETE)),
) -> Result[None]:
    await service.delete_workspace(session, ws_id)
    await write_audit_log(
        session,
        actor_user_id=audit.actor_user_id,
        actor_username=audit.actor_username,
        action="workspace.delete",
        resource_type="workspace",
        resource_id=ws_id,
        ip=audit.ip,
        user_agent=audit.user_agent,
        request_id=audit.request_id,
    )
    return Result.ok(None)


# ── members CRUD ───────────────────────────────────────


@router.get("/{ws_id}/members", response_model=Result[list[MemberItem]])
async def list_members(
    ws_id: int,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission(_PERM_READ)),
) -> Result[list[MemberItem]]:
    return Result.ok(await service.list_members(session, ws_id))


@router.post("/{ws_id}/members", response_model=Result[MemberItem])
async def add_member(
    ws_id: int,
    req: AddMemberRequest,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission(_PERM_WRITE)),
) -> Result[MemberItem]:
    return Result.ok(await service.add_member(session, ws_id, req))


@router.post(
    "/{ws_id}/members/{membership_id}/update", response_model=Result[MemberItem]
)
async def update_member_role(
    ws_id: int,
    membership_id: int,
    req: UpdateMemberRoleRequest,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission(_PERM_WRITE)),
) -> Result[MemberItem]:
    return Result.ok(
        await service.update_member_role(session, ws_id, membership_id, req)
    )


@router.post(
    "/{ws_id}/members/{membership_id}/delete", response_model=Result[None]
)
async def remove_member(
    ws_id: int,
    membership_id: int,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission(_PERM_WRITE)),
) -> Result[None]:
    await service.remove_member(session, ws_id, membership_id)
    return Result.ok(None)


# ── quota ───────────────────────────────────────────────


@router.get("/{ws_id}/quota", response_model=Result[QuotaItem])
async def get_quota(
    ws_id: int,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission(_PERM_READ)),
) -> Result[QuotaItem]:
    return Result.ok(await service.get_quota(session, ws_id))


@router.post("/{ws_id}/quota/update", response_model=Result[QuotaItem])
async def update_quota(
    ws_id: int,
    req: UpdateQuotaRequest,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission(_PERM_WRITE)),
) -> Result[QuotaItem]:
    return Result.ok(await service.update_quota(session, ws_id, req))
