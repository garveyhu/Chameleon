"""apps + app_agents HTTP 路由

挂点：/v1/admin/apps/*
关联：apps + api_keys（子列表）+ app_agents（授权 agent 多对多）
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.api.exceptions import (
    BusinessError,
    ResultCode,
    ValidationError,
)
from chameleon.core.api.response import PageParams, PageResult, Result
from chameleon.core.infra.db import get_session
from chameleon.core.models import Agent, ApiKey, App, AppAgent
from chameleon.system.api_key.schemas import ApiKeyItem
from chameleon.system.auth.dependencies import require_permission


# ── DTO ─────────────────────────────────────────────────────


class AppItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    app_key: str
    name: str
    description: str | None = None
    status: str
    owner_user_id: int | None = None
    meta: dict | None = None
    qpm_limit: int | None = None
    qpd_limit: int | None = None
    created_at: datetime
    updated_at: datetime


class CreateAppRequest(BaseModel):
    app_key: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    description: str | None = None
    qpm_limit: int | None = Field(default=None, ge=0)
    qpd_limit: int | None = Field(default=None, ge=0)


class UpdateAppRequest(BaseModel):
    name: str | None = Field(default=None, max_length=128)
    description: str | None = None
    status: str | None = Field(default=None, pattern="^(active|suspended)$")
    qpm_limit: int | None = Field(default=None, ge=0)
    qpd_limit: int | None = Field(default=None, ge=0)


class GrantAgentRequest(BaseModel):
    agent_key: str


# ── 路由 ────────────────────────────────────────────────────


router = APIRouter(prefix="/v1/admin/apps", tags=["admin:apps"])


@router.get("", response_model=Result[PageResult[AppItem]])
async def list_apps(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("apps:read")),
) -> Result[PageResult[AppItem]]:
    base = select(App).where(App.deleted_at.is_(None))
    total = (
        await session.execute(select(func.count()).select_from(base.subquery()))
    ).scalar_one()
    rows = (
        (
            await session.execute(
                base.order_by(App.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        .scalars()
        .all()
    )
    return Result.ok(
        PageResult(
            items=[AppItem.model_validate(a) for a in rows],
            total=total,
            page=page,
            page_size=page_size,
        )
    )


@router.get("/{app_id}", response_model=Result[AppItem])
async def get_app(
    app_id: int,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("apps:read")),
) -> Result[AppItem]:
    app = (
        await session.execute(
            select(App).where(App.id == app_id, App.deleted_at.is_(None))
        )
    ).scalar_one_or_none()
    if app is None:
        raise BusinessError(ResultCode.AgentNotFound, message=f"app 不存在: {app_id}")
    return Result.ok(AppItem.model_validate(app))


async def _flush_refresh_validate(session: AsyncSession, app: App) -> AppItem:
    """flush + refresh 让 updated_at 等 server_default 字段落地"""
    await session.flush()
    await session.refresh(app)
    return AppItem.model_validate(app)


@router.post("", response_model=Result[AppItem])
async def create_app(
    req: CreateAppRequest,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("apps:write")),
) -> Result[AppItem]:
    existing = (
        await session.execute(select(App).where(App.app_key == req.app_key))
    ).scalar_one_or_none()
    if existing is not None:
        raise ValidationError(message=f"app_key 已存在: {req.app_key}")
    app = App(
        app_key=req.app_key,
        name=req.name,
        description=req.description,
        qpm_limit=req.qpm_limit,
        qpd_limit=req.qpd_limit,
        status="active",
    )
    session.add(app)
    return Result.ok(await _flush_refresh_validate(session, app))


@router.post("/{app_id}/update", response_model=Result[AppItem])
async def update_app(
    app_id: int,
    req: UpdateAppRequest,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("apps:write")),
) -> Result[AppItem]:
    app = (
        await session.execute(
            select(App).where(App.id == app_id, App.deleted_at.is_(None))
        )
    ).scalar_one_or_none()
    if app is None:
        raise BusinessError(ResultCode.AgentNotFound, message=f"app 不存在: {app_id}")
    if req.name is not None:
        app.name = req.name
    if req.description is not None:
        app.description = req.description
    if req.status is not None:
        app.status = req.status
    if req.qpm_limit is not None:
        app.qpm_limit = req.qpm_limit
    if req.qpd_limit is not None:
        app.qpd_limit = req.qpd_limit
    return Result.ok(await _flush_refresh_validate(session, app))


@router.post("/{app_id}/delete", response_model=Result[None])
async def delete_app(
    app_id: int,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("apps:delete")),
) -> Result[None]:
    app = (
        await session.execute(
            select(App).where(App.id == app_id, App.deleted_at.is_(None))
        )
    ).scalar_one_or_none()
    if app is None:
        raise BusinessError(ResultCode.AgentNotFound, message=f"app 不存在: {app_id}")
    app.deleted_at = datetime.now(timezone.utc)
    app.app_key = f"__deleted_{app.id}_{app.app_key}"
    await session.flush()
    return Result.ok(None)


# ── api_keys 子列表（apps 视角） ─────────────────────────────


@router.get("/{app_id}/api-keys", response_model=Result[list[ApiKeyItem]])
async def list_app_api_keys(
    app_id: int,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("api_keys:read")),
) -> Result[list[ApiKeyItem]]:
    app = (
        await session.execute(select(App).where(App.id == app_id))
    ).scalar_one_or_none()
    if app is None:
        raise BusinessError(ResultCode.AgentNotFound, message=f"app 不存在: {app_id}")
    rows = (
        (
            await session.execute(
                select(ApiKey)
                .where(ApiKey.app_id == app.app_key)
                .order_by(ApiKey.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return Result.ok([ApiKeyItem.model_validate(k) for k in rows])


# ── app_agents 授权 ─────────────────────────────────────────


@router.post("/{app_id}/agents/grant", response_model=Result[None])
async def grant_agent(
    app_id: int,
    req: GrantAgentRequest,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("apps:write")),
) -> Result[None]:
    agent = (
        await session.execute(
            select(Agent).where(
                Agent.agent_key == req.agent_key, Agent.deleted_at.is_(None)
            )
        )
    ).scalar_one_or_none()
    if agent is None:
        raise BusinessError(
            ResultCode.AgentNotFound, message=f"agent 不存在: {req.agent_key}"
        )
    existing = (
        await session.execute(
            select(AppAgent).where(
                AppAgent.app_id == app_id, AppAgent.agent_id == agent.id
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        session.add(AppAgent(app_id=app_id, agent_id=agent.id))
        await session.flush()
    return Result.ok(None)


@router.post("/{app_id}/agents/revoke", response_model=Result[None])
async def revoke_agent(
    app_id: int,
    req: GrantAgentRequest,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("apps:write")),
) -> Result[None]:
    agent = (
        await session.execute(
            select(Agent).where(Agent.agent_key == req.agent_key)
        )
    ).scalar_one_or_none()
    if agent is None:
        raise BusinessError(
            ResultCode.AgentNotFound, message=f"agent 不存在: {req.agent_key}"
        )
    await session.execute(
        delete(AppAgent).where(
            AppAgent.app_id == app_id, AppAgent.agent_id == agent.id
        )
    )
    await session.flush()
    return Result.ok(None)


@router.get("/{app_id}/agents", response_model=Result[list[str]])
async def list_app_agents(
    app_id: int,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("apps:read")),
) -> Result[list[str]]:
    rows = (
        await session.execute(
            select(Agent.agent_key)
            .join(AppAgent, AppAgent.agent_id == Agent.id)
            .where(AppAgent.app_id == app_id, Agent.deleted_at.is_(None))
            .order_by(Agent.agent_key)
        )
    ).all()
    return Result.ok([r[0] for r in rows])
