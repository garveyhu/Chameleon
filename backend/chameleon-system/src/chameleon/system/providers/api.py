"""providers HTTP 路由

挂点：/v1/admin/providers/*
api_key 写入用 AES-256-GCM 加密；改动后调 reload_llm_cache 让 LLM 实例新值生效。
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
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
from chameleon.core.models import Provider
from chameleon.core.utils.crypto import encrypt
from chameleon.system.auth.dependencies import require_permission


# ── DTO ────────────────────────────────────────────────────


class ProviderItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    kind: str
    name: str
    base_url: str | None = None
    has_api_key: bool = False  # 不返加密文，仅告知是否已配
    extra_config: dict | None = None
    enabled: bool
    description: str | None = None
    created_at: datetime
    updated_at: datetime


def _to_item(p: Provider) -> ProviderItem:
    return ProviderItem(
        id=p.id,
        code=p.code,
        kind=p.kind,
        name=p.name,
        base_url=p.base_url,
        has_api_key=bool(p.api_key_encrypted),
        extra_config=p.extra_config,
        enabled=p.enabled,
        description=p.description,
        created_at=p.created_at,
        updated_at=p.updated_at,
    )


class CreateProviderRequest(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    kind: str = Field(pattern="^(llm|embedding|dify|fastgpt|coze)$")
    name: str = Field(min_length=1, max_length=128)
    base_url: str | None = None
    api_key: str | None = None
    extra_config: dict | None = None
    description: str | None = None


class UpdateProviderRequest(BaseModel):
    name: str | None = None
    base_url: str | None = None
    api_key: str | None = Field(default=None, description="非空才更新；空字符串 → 清空")
    extra_config: dict | None = None
    enabled: bool | None = None
    description: str | None = None


# ── 路由 ───────────────────────────────────────────────────


router = APIRouter(prefix="/v1/admin/providers", tags=["admin:providers"])


@router.get("", response_model=Result[list[ProviderItem]])
async def list_providers(
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("providers:read")),
) -> Result[list[ProviderItem]]:
    rows = (
        (
            await session.execute(
                select(Provider)
                .where(Provider.deleted_at.is_(None))
                .order_by(Provider.code)
            )
        )
        .scalars()
        .all()
    )
    return Result.ok([_to_item(p) for p in rows])


@router.post("", response_model=Result[ProviderItem])
async def create_provider(
    req: CreateProviderRequest,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("providers:write")),
) -> Result[ProviderItem]:
    existing = (
        await session.execute(
            select(Provider).where(Provider.code == req.code)
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise ValidationError(message=f"provider code 已存在: {req.code}")
    p = Provider(
        code=req.code,
        kind=req.kind,
        name=req.name,
        base_url=req.base_url,
        api_key_encrypted=encrypt(req.api_key) if req.api_key else None,
        extra_config=req.extra_config,
        description=req.description,
        enabled=True,
    )
    session.add(p)
    await session.flush()
    await session.commit()  # 提早 commit 让 reload 读到
    await reload_llm_cache()
    return Result.ok(_to_item(p))


@router.post("/{provider_id}/update", response_model=Result[ProviderItem])
async def update_provider(
    provider_id: int,
    req: UpdateProviderRequest,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("providers:write")),
) -> Result[ProviderItem]:
    p = (
        await session.execute(
            select(Provider).where(
                Provider.id == provider_id, Provider.deleted_at.is_(None)
            )
        )
    ).scalar_one_or_none()
    if p is None:
        raise BusinessError(
            ResultCode.AgentNotFound, message=f"provider 不存在: {provider_id}"
        )
    if req.name is not None:
        p.name = req.name
    if req.base_url is not None:
        p.base_url = req.base_url
    if req.api_key is not None:
        # 空字符串 → 清空 api_key（不加密）
        p.api_key_encrypted = encrypt(req.api_key) if req.api_key else None
    if req.extra_config is not None:
        p.extra_config = req.extra_config
    if req.enabled is not None:
        p.enabled = req.enabled
    if req.description is not None:
        p.description = req.description
    await session.flush()
    await session.commit()
    await reload_llm_cache()
    return Result.ok(_to_item(p))


@router.post("/{provider_id}/delete", response_model=Result[None])
async def delete_provider(
    provider_id: int,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("providers:delete")),
) -> Result[None]:
    p = (
        await session.execute(
            select(Provider).where(
                Provider.id == provider_id, Provider.deleted_at.is_(None)
            )
        )
    ).scalar_one_or_none()
    if p is None:
        raise BusinessError(
            ResultCode.AgentNotFound, message=f"provider 不存在: {provider_id}"
        )
    p.deleted_at = datetime.now(timezone.utc)
    p.code = f"__deleted_{p.id}_{p.code}"
    await session.flush()
    await session.commit()
    await reload_llm_cache()
    return Result.ok(None)


# provider test 已迁移到 model 级 —— 见 chameleon.system.models.api.test_model
# provider 只是凭证容器，是否真正可用要看具体模型能不能调起来。
