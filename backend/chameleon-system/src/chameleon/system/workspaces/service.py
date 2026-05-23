"""workspace admin service —— workspace CRUD + members CRUD

红线（plan §5.2 + §2）：
- ⛔ default workspace (id=1) 永不可删 —— uninstall 拒绝
- ⛔ workspace_key 唯一；workspace 软删（deleted_at）防误关业务
- ⛔ memberships 同 (user, ws, team) 防重 —— PG NULL distinct 不挡，service 兜底
"""

from __future__ import annotations

from datetime import datetime, timezone

from loguru import logger
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.api.exceptions import BusinessError, ResultCode
from chameleon.core.models import Membership, User, Workspace, WorkspaceQuota
from chameleon.core.models.workspace import DEFAULT_WORKSPACE_ID
from chameleon.system.workspaces.quota_service import (
    get_or_create_quota,
    snapshot as quota_snapshot,
)
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


# ── workspace CRUD ──────────────────────────────────────


async def list_workspaces(session: AsyncSession) -> list[WorkspaceItem]:
    rows = (
        (
            await session.execute(
                select(Workspace)
                .where(Workspace.deleted_at.is_(None))
                .order_by(Workspace.id != DEFAULT_WORKSPACE_ID, Workspace.created_at)
            )
        )
        .scalars()
        .all()
    )
    return [WorkspaceItem.model_validate(r) for r in rows]


async def get_workspace(session: AsyncSession, ws_id: int) -> WorkspaceItem:
    return WorkspaceItem.model_validate(await _load(session, ws_id))


async def create_workspace(
    session: AsyncSession, req: CreateWorkspaceRequest
) -> WorkspaceItem:
    exists = (
        await session.execute(
            select(Workspace.id).where(
                Workspace.workspace_key == req.workspace_key
            )
        )
    ).scalar_one_or_none()
    if exists is not None:
        raise BusinessError(
            ResultCode.Fail,
            message=f"workspace_key 已存在: {req.workspace_key}",
        )
    ws = Workspace(
        workspace_key=req.workspace_key,
        name=req.name,
        plan=req.plan,
        config=req.config,
    )
    session.add(ws)
    await session.flush()
    await session.refresh(ws)
    # 同步建配额行
    session.add(
        WorkspaceQuota(
            workspace_id=ws.id, reset_at=datetime.now(timezone.utc)
        )
    )
    item = WorkspaceItem.model_validate(ws)
    await session.commit()
    logger.info("workspace created | id={} | key={}", ws.id, ws.workspace_key)
    return item


async def update_workspace(
    session: AsyncSession, ws_id: int, req: UpdateWorkspaceRequest
) -> WorkspaceItem:
    ws = await _load(session, ws_id)
    if req.name is not None:
        ws.name = req.name
    if req.plan is not None:
        ws.plan = req.plan
    if req.config is not None:
        ws.config = req.config
    await session.flush()
    await session.refresh(ws)
    item = WorkspaceItem.model_validate(ws)
    await session.commit()
    return item


async def delete_workspace(session: AsyncSession, ws_id: int) -> None:
    if ws_id == DEFAULT_WORKSPACE_ID:
        raise BusinessError(
            ResultCode.Fail, message="默认 workspace 不可删除"
        )
    ws = await _load(session, ws_id)
    ws.deleted_at = datetime.now(timezone.utc)
    await session.flush()
    await session.commit()
    logger.info("workspace soft-deleted | id={}", ws_id)


# ── members CRUD ────────────────────────────────────────


async def list_members(
    session: AsyncSession, ws_id: int
) -> list[MemberItem]:
    rows = (
        (
            await session.execute(
                select(Membership, User.username)
                .join(User, Membership.user_id == User.id)
                .where(Membership.workspace_id == ws_id)
                .order_by(Membership.created_at)
            )
        )
        .all()
    )
    out: list[MemberItem] = []
    for m, username in rows:
        item = MemberItem.model_validate(m)
        item = item.model_copy(update={"username": username})
        out.append(item)
    return out


async def add_member(
    session: AsyncSession, ws_id: int, req: AddMemberRequest
) -> MemberItem:
    await _load(session, ws_id)  # 校验存在
    # 校验 user 存在
    user = (
        await session.execute(select(User).where(User.id == req.user_id))
    ).scalar_one_or_none()
    if user is None:
        raise BusinessError(
            ResultCode.Fail, message=f"用户不存在: {req.user_id}"
        )
    # 防重（service 兜底 PG NULL distinct 漏洞）
    dup = (
        await session.execute(
            select(Membership).where(
                Membership.user_id == req.user_id,
                Membership.workspace_id == ws_id,
                Membership.team_id.is_(None)
                if req.team_id is None
                else Membership.team_id == req.team_id,
            )
        )
    ).scalar_one_or_none()
    if dup is not None:
        raise BusinessError(
            ResultCode.Fail,
            message=f"成员已存在: user={req.user_id} ws={ws_id} team={req.team_id}",
        )

    m = Membership(
        user_id=req.user_id,
        workspace_id=ws_id,
        team_id=req.team_id,
        role=req.role,
    )
    session.add(m)
    await session.flush()
    await session.refresh(m)
    await session.commit()

    item = MemberItem.model_validate(m)
    return item.model_copy(update={"username": user.username})


async def update_member_role(
    session: AsyncSession,
    ws_id: int,
    membership_id: int,
    req: UpdateMemberRoleRequest,
) -> MemberItem:
    m = (
        await session.execute(
            select(Membership).where(
                Membership.id == membership_id,
                Membership.workspace_id == ws_id,
            )
        )
    ).scalar_one_or_none()
    if m is None:
        raise BusinessError(
            ResultCode.NotFound,
            message=f"成员关系不存在: ws={ws_id} mid={membership_id}",
        )
    m.role = req.role
    await session.flush()
    await session.refresh(m)
    await session.commit()

    username = (
        await session.execute(select(User.username).where(User.id == m.user_id))
    ).scalar_one_or_none()
    item = MemberItem.model_validate(m)
    return item.model_copy(update={"username": username})


async def remove_member(
    session: AsyncSession, ws_id: int, membership_id: int
) -> None:
    r = await session.execute(
        delete(Membership).where(
            Membership.id == membership_id,
            Membership.workspace_id == ws_id,
        )
    )
    await session.commit()
    if r.rowcount == 0:
        raise BusinessError(
            ResultCode.NotFound,
            message=f"成员关系不存在: ws={ws_id} mid={membership_id}",
        )


# ── quota ───────────────────────────────────────────────


async def get_quota(session: AsyncSession, ws_id: int) -> QuotaItem:
    await _load(session, ws_id)  # 校验 ws 存在
    snap = await quota_snapshot(session, ws_id)
    return QuotaItem(
        workspace_id=snap.workspace_id,
        token_quota_monthly=snap.token_quota_monthly,
        token_used_current_month=snap.token_used_current_month,
        request_quota_daily=snap.request_quota_daily,
        request_used_today=snap.request_used_today,
        reset_at=snap.reset_at,
    )


async def update_quota(
    session: AsyncSession, ws_id: int, req: UpdateQuotaRequest
) -> QuotaItem:
    await _load(session, ws_id)
    quota = await get_or_create_quota(session, ws_id)
    quota.token_quota_monthly = req.token_quota_monthly
    quota.request_quota_daily = req.request_quota_daily
    if req.reset_used:
        quota.token_used_current_month = 0
        quota.request_used_today = 0
        quota.reset_at = datetime.now(timezone.utc)
    await session.flush()
    await session.refresh(quota)
    await session.commit()
    return await get_quota(session, ws_id)


# ── helpers ─────────────────────────────────────────────


async def _load(session: AsyncSession, ws_id: int) -> Workspace:
    row = (
        await session.execute(
            select(Workspace).where(
                Workspace.id == ws_id, Workspace.deleted_at.is_(None)
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise BusinessError(
            ResultCode.NotFound, message=f"workspace 不存在: {ws_id}"
        )
    return row
