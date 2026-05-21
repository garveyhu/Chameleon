"""embed_configs admin HTTP 路由 (/v1/admin/embed-configs)"""

from __future__ import annotations

import secrets
import string
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.api.exceptions import (
    BusinessError,
    ResultCode,
    ValidationError,
)
from chameleon.core.api.response import PageResult, Result
from chameleon.core.infra.db import get_session
from chameleon.core.models import Agent, App, EmbedConfig
from chameleon.system.auth.dependencies import (
    CurrentUser,
    get_current_user,
    require_permission,
)


# ── DTO ────────────────────────────────────────────────────


class EmbedConfigItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    embed_key: str
    name: str
    description: str | None = None
    agent_id: int
    app_id: int
    allowed_origins: list | None = None
    ui_config: dict | None = None
    behavior: dict | None = None
    enabled: bool
    created_by_user_id: int | None = None
    created_at: datetime
    updated_at: datetime


class CreateEmbedConfigRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str | None = None
    agent_id: int
    app_id: int
    allowed_origins: list[str] = Field(
        default_factory=list,
        description="域名白名单，如 ['https://example.com']；为空表示拒绝所有跨域",
    )
    ui_config: dict | None = None
    behavior: dict | None = None


class UpdateEmbedConfigRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    allowed_origins: list[str] | None = None
    ui_config: dict | None = None
    behavior: dict | None = None
    enabled: bool | None = None


# ── helpers ────────────────────────────────────────────────


_EMBED_KEY_ALPHABET = string.ascii_letters + string.digits
_EMBED_KEY_LEN = 8


def _generate_embed_key() -> str:
    body = "".join(secrets.choice(_EMBED_KEY_ALPHABET) for _ in range(_EMBED_KEY_LEN))
    return f"emb_{body}"


async def _flush_refresh(session: AsyncSession, e: EmbedConfig) -> EmbedConfigItem:
    await session.flush()
    await session.refresh(e)
    return EmbedConfigItem.model_validate(e)


# ── 路由 ──────────────────────────────────────────────────


router = APIRouter(
    prefix="/v1/admin/embed-configs", tags=["admin:embed-configs"]
)


@router.get("", response_model=Result[PageResult[EmbedConfigItem]])
async def list_embed_configs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("embed_configs:read")),
) -> Result[PageResult[EmbedConfigItem]]:
    base = select(EmbedConfig).where(EmbedConfig.deleted_at.is_(None))
    total = (
        await session.execute(select(func.count()).select_from(base.subquery()))
    ).scalar_one()
    rows = (
        (
            await session.execute(
                base.order_by(EmbedConfig.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        .scalars()
        .all()
    )
    return Result.ok(
        PageResult(
            items=[EmbedConfigItem.model_validate(r) for r in rows],
            total=total,
            page=page,
            page_size=page_size,
        )
    )


@router.get("/{config_id}", response_model=Result[EmbedConfigItem])
async def get_embed_config(
    config_id: int,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("embed_configs:read")),
) -> Result[EmbedConfigItem]:
    e = (
        await session.execute(
            select(EmbedConfig).where(
                EmbedConfig.id == config_id, EmbedConfig.deleted_at.is_(None)
            )
        )
    ).scalar_one_or_none()
    if e is None:
        raise BusinessError(
            ResultCode.AgentNotFound, message=f"embed_config 不存在: {config_id}"
        )
    return Result.ok(EmbedConfigItem.model_validate(e))


@router.post("", response_model=Result[EmbedConfigItem])
async def create_embed_config(
    req: CreateEmbedConfigRequest,
    session: AsyncSession = Depends(get_session),
    user: CurrentUser = Depends(get_current_user),
    __: object = Depends(require_permission("embed_configs:write")),
) -> Result[EmbedConfigItem]:
    # 校验 agent / app 存在
    agent = (
        await session.execute(
            select(Agent).where(
                Agent.id == req.agent_id, Agent.deleted_at.is_(None)
            )
        )
    ).scalar_one_or_none()
    if agent is None:
        raise ValidationError(message=f"agent 不存在: {req.agent_id}")
    app = (
        await session.execute(
            select(App).where(App.id == req.app_id, App.deleted_at.is_(None))
        )
    ).scalar_one_or_none()
    if app is None:
        raise ValidationError(message=f"app 不存在: {req.app_id}")

    # 生成唯一 embed_key（极小概率冲突，重试一次）
    for _ in range(3):
        key = _generate_embed_key()
        exists = (
            await session.execute(
                select(EmbedConfig).where(EmbedConfig.embed_key == key)
            )
        ).scalar_one_or_none()
        if exists is None:
            break
    else:
        raise BusinessError(
            ResultCode.InternalError, message="embed_key 生成多次冲突，请重试"
        )

    e = EmbedConfig(
        embed_key=key,
        name=req.name,
        description=req.description,
        agent_id=req.agent_id,
        app_id=req.app_id,
        allowed_origins=req.allowed_origins or None,
        ui_config=req.ui_config,
        behavior=req.behavior,
        enabled=True,
        created_by_user_id=user.id,
    )
    session.add(e)
    return Result.ok(await _flush_refresh(session, e))


@router.post("/{config_id}/update", response_model=Result[EmbedConfigItem])
async def update_embed_config(
    config_id: int,
    req: UpdateEmbedConfigRequest,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("embed_configs:write")),
) -> Result[EmbedConfigItem]:
    e = (
        await session.execute(
            select(EmbedConfig).where(
                EmbedConfig.id == config_id, EmbedConfig.deleted_at.is_(None)
            )
        )
    ).scalar_one_or_none()
    if e is None:
        raise BusinessError(
            ResultCode.AgentNotFound, message=f"embed_config 不存在: {config_id}"
        )
    if req.name is not None:
        e.name = req.name
    if req.description is not None:
        e.description = req.description
    if req.allowed_origins is not None:
        e.allowed_origins = req.allowed_origins or None
    if req.ui_config is not None:
        e.ui_config = req.ui_config
    if req.behavior is not None:
        e.behavior = req.behavior
    if req.enabled is not None:
        e.enabled = req.enabled
    return Result.ok(await _flush_refresh(session, e))


@router.post("/{config_id}/delete", response_model=Result[None])
async def delete_embed_config(
    config_id: int,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("embed_configs:delete")),
) -> Result[None]:
    e = (
        await session.execute(
            select(EmbedConfig).where(
                EmbedConfig.id == config_id, EmbedConfig.deleted_at.is_(None)
            )
        )
    ).scalar_one_or_none()
    if e is None:
        raise BusinessError(
            ResultCode.AgentNotFound, message=f"embed_config 不存在: {config_id}"
        )
    e.deleted_at = datetime.now(timezone.utc)
    e.embed_key = f"__deleted_{e.id}_{e.embed_key}"
    await session.flush()
    return Result.ok(None)
