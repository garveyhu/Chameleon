"""eval_templates HTTP 路由（/v1/admin/eval-templates）"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.api.response import PageParams, PageResult, Result
from chameleon.data.infra.db import get_session
from chameleon.system.auth.dependencies import require_permission
from chameleon.system.eval_templates import service as et_service
from chameleon.system.eval_templates.schemas import (
    CreateEvalTemplateRequest,
    EvalTemplateItem,
    UpdateEvalTemplateRequest,
)

router = APIRouter(prefix="/v1/admin/eval-templates", tags=["admin:eval-templates"])


@router.get("", response_model=Result[PageResult[EvalTemplateItem]])
async def list_templates(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    keyword: str | None = Query(None),
    sort_by: str = Query("updated_at"),
    order: str = Query("desc"),
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("datasets:read")),
) -> Result[PageResult[EvalTemplateItem]]:
    return Result.ok(
        await et_service.list_templates(
            session,
            PageParams(page=page, page_size=page_size),
            keyword=keyword,
            sort_by=sort_by,
            order=order,
        )
    )


@router.get("/{template_id}", response_model=Result[EvalTemplateItem])
async def get_template(
    template_id: int,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("datasets:read")),
) -> Result[EvalTemplateItem]:
    return Result.ok(await et_service.get_template(session, template_id))


@router.post("", response_model=Result[EvalTemplateItem])
async def create_template(
    req: CreateEvalTemplateRequest,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("datasets:write")),
) -> Result[EvalTemplateItem]:
    return Result.ok(await et_service.create_template(session, req))


@router.post("/{template_id}/update", response_model=Result[EvalTemplateItem])
async def update_template(
    template_id: int,
    req: UpdateEvalTemplateRequest,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("datasets:write")),
) -> Result[EvalTemplateItem]:
    return Result.ok(await et_service.update_template(session, template_id, req))


@router.post("/{template_id}/delete", response_model=Result[None])
async def delete_template(
    template_id: int,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("datasets:delete")),
) -> Result[None]:
    await et_service.delete_template(session, template_id)
    return Result.ok(None)
