"""models HTTP 路由 (/v1/admin/models)"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.api.exceptions import (
    BusinessError,
    ResultCode,
    ValidationError,
)
from chameleon.core.api.response import Result
from chameleon.core.components.llms.factory import reload_llm_cache
from chameleon.core.infra.db import get_session
from chameleon.core.models import LLMModel, Provider
from chameleon.system.auth.dependencies import require_permission


class ModelItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    provider_id: int
    provider_code: str | None = None
    code: str
    kind: str
    dim: int | None = None
    defaults: dict | None = None
    enabled: bool
    created_at: datetime
    updated_at: datetime


class CreateModelRequest(BaseModel):
    provider_id: int
    code: str = Field(min_length=1, max_length=128)
    kind: str = Field(pattern="^(chat|embedding)$")
    dim: int | None = None
    defaults: dict | None = None


class UpdateModelRequest(BaseModel):
    dim: int | None = None
    defaults: dict | None = None
    enabled: bool | None = None


def _to_item(m: LLMModel, provider_code: str | None = None) -> ModelItem:
    return ModelItem(
        id=m.id,
        provider_id=m.provider_id,
        provider_code=provider_code,
        code=m.code,
        kind=m.kind,
        dim=m.dim,
        defaults=m.defaults,
        enabled=m.enabled,
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


router = APIRouter(prefix="/v1/admin/models", tags=["admin:models"])


@router.get("", response_model=Result[list[ModelItem]])
async def list_models(
    kind: str | None = Query(default=None, pattern="^(chat|embedding)$"),
    provider_id: int | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("models:read")),
) -> Result[list[ModelItem]]:
    stmt = (
        select(LLMModel, Provider.code)
        .join(Provider, LLMModel.provider_id == Provider.id)
        .where(LLMModel.deleted_at.is_(None))
        .order_by(LLMModel.kind, LLMModel.code)
    )
    if kind:
        stmt = stmt.where(LLMModel.kind == kind)
    if provider_id:
        stmt = stmt.where(LLMModel.provider_id == provider_id)
    rows = (await session.execute(stmt)).all()
    return Result.ok([_to_item(m, pcode) for m, pcode in rows])


@router.post("", response_model=Result[ModelItem])
async def create_model(
    req: CreateModelRequest,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("models:write")),
) -> Result[ModelItem]:
    provider = (
        await session.execute(
            select(Provider).where(
                Provider.id == req.provider_id, Provider.deleted_at.is_(None)
            )
        )
    ).scalar_one_or_none()
    if provider is None:
        raise ValidationError(message=f"provider 不存在: {req.provider_id}")

    existing = (
        await session.execute(
            select(LLMModel).where(
                LLMModel.provider_id == req.provider_id,
                LLMModel.code == req.code,
                LLMModel.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise ValidationError(message=f"同 provider 已有同 code 的 model: {req.code}")

    m = LLMModel(
        provider_id=req.provider_id,
        code=req.code,
        kind=req.kind,
        dim=req.dim,
        defaults=req.defaults,
        enabled=True,
    )
    session.add(m)
    await session.flush()
    await session.commit()
    await reload_llm_cache()
    return Result.ok(_to_item(m, provider.code))


@router.post("/{model_id}/update", response_model=Result[ModelItem])
async def update_model(
    model_id: int,
    req: UpdateModelRequest,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("models:write")),
) -> Result[ModelItem]:
    m = (
        await session.execute(
            select(LLMModel).where(
                LLMModel.id == model_id, LLMModel.deleted_at.is_(None)
            )
        )
    ).scalar_one_or_none()
    if m is None:
        raise BusinessError(
            ResultCode.AgentNotFound, message=f"model 不存在: {model_id}"
        )
    if req.dim is not None:
        m.dim = req.dim
    if req.defaults is not None:
        m.defaults = req.defaults
    if req.enabled is not None:
        m.enabled = req.enabled
    await session.flush()
    await session.commit()
    await reload_llm_cache()
    return Result.ok(_to_item(m))


@router.post("/{model_id}/delete", response_model=Result[None])
async def delete_model(
    model_id: int,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("models:delete")),
) -> Result[None]:
    m = (
        await session.execute(
            select(LLMModel).where(
                LLMModel.id == model_id, LLMModel.deleted_at.is_(None)
            )
        )
    ).scalar_one_or_none()
    if m is None:
        raise BusinessError(
            ResultCode.AgentNotFound, message=f"model 不存在: {model_id}"
        )
    m.deleted_at = datetime.now(timezone.utc)
    await session.flush()
    await session.commit()
    await reload_llm_cache()
    return Result.ok(None)
