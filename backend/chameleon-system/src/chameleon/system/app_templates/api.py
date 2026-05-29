"""app_templates HTTP 路由（/v1/admin/app-templates）"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.api.response import Result
from chameleon.data.infra.db import get_session
from chameleon.system.app_templates import service as t_service
from chameleon.system.app_templates.schemas import (
    AppTemplateItem,
    CreateAppTemplateRequest,
    InstallTemplateResult,
)
from chameleon.system.auth.dependencies import require_permission

router = APIRouter(
    prefix="/v1/admin/app-templates", tags=["admin:app-templates"]
)


@router.get("", response_model=Result[list[AppTemplateItem]])
async def list_templates(
    only_verified: bool = Query(default=True),
    category: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("plugins:read")),
) -> Result[list[AppTemplateItem]]:
    """list；默认 only_verified=True（红线：自传 template 不进默认列表）"""
    items = await t_service.list_templates(
        session,
        only_verified=only_verified,
        category=category,
        limit=limit,
    )
    return Result.ok(items)


@router.get("/{template_id}", response_model=Result[AppTemplateItem])
async def get_template(
    template_id: int,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("plugins:read")),
) -> Result[AppTemplateItem]:
    return Result.ok(await t_service.get_template(session, template_id))


@router.post("", response_model=Result[AppTemplateItem])
async def create_template(
    req: CreateAppTemplateRequest,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("plugins:write")),
) -> Result[AppTemplateItem]:
    """新建（默认 verified=False；要进默认列表得管理员另调 /verify）"""
    return Result.ok(
        await t_service.create_template(
            session, req, created_by_user_id=None
        )
    )


class VerifyRequest(BaseModel):
    verified: bool


@router.post(
    "/{template_id}/verify", response_model=Result[AppTemplateItem]
)
async def verify_template(
    template_id: int,
    req: VerifyRequest,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("plugins:write")),
) -> Result[AppTemplateItem]:
    """admin 审核；verified=True 才进默认列表"""
    return Result.ok(
        await t_service.verify_template(
            session, template_id, verified=req.verified
        )
    )


@router.post(
    "/{template_id}/install", response_model=Result[InstallTemplateResult]
)
async def install_template(
    template_id: int,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("plugins:write")),
) -> Result[InstallTemplateResult]:
    return Result.ok(
        await t_service.install_template(session, template_id)
    )


@router.post("/{template_id}/delete", response_model=Result[None])
async def delete_template(
    template_id: int,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("plugins:delete")),
) -> Result[None]:
    await t_service.delete_template(session, template_id)
    return Result.ok(None)
