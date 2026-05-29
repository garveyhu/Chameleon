"""eval_jobs HTTP 路由（/v1/admin/eval-jobs）"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.api.response import Result
from chameleon.data.infra.db import get_session
from chameleon.system.auth.dependencies import require_permission
from chameleon.system.eval_jobs import scheduler, service
from chameleon.system.eval_jobs.schemas import (
    CreateEvalJobRequest,
    EvalJobItem,
    EvalJobRunItem,
    TriggerEvalJobResult,
    UpdateEvalJobRequest,
)

router = APIRouter(prefix="/v1/admin/eval-jobs", tags=["admin:eval-jobs"])


# ── CRUD ────────────────────────────────────────────────


@router.get("", response_model=Result[list[EvalJobItem]])
async def list_jobs(
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("datasets:read")),
) -> Result[list[EvalJobItem]]:
    items = await service.list_jobs(session)
    return Result.ok(items)


@router.get("/{job_id}", response_model=Result[EvalJobItem])
async def get_job(
    job_id: int,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("datasets:read")),
) -> Result[EvalJobItem]:
    item = await service.get_job(session, job_id)
    return Result.ok(item)


@router.post("", response_model=Result[EvalJobItem])
async def create_job(
    req: CreateEvalJobRequest,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("datasets:write")),
) -> Result[EvalJobItem]:
    item = await service.create_job(session, req)
    await scheduler.sync_job(item.id)
    return Result.ok(item)


@router.post("/{job_id}/update", response_model=Result[EvalJobItem])
async def update_job(
    job_id: int,
    req: UpdateEvalJobRequest,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("datasets:write")),
) -> Result[EvalJobItem]:
    item = await service.update_job(session, job_id, req)
    await scheduler.sync_job(item.id)
    return Result.ok(item)


@router.post("/{job_id}/delete", response_model=Result[None])
async def delete_job(
    job_id: int,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("datasets:delete")),
) -> Result[None]:
    await service.delete_job(session, job_id)
    scheduler.remove_job(job_id)
    return Result.ok(None)


# ── trigger / runs 查询 ─────────────────────────────────


@router.post("/{job_id}/trigger", response_model=Result[TriggerEvalJobResult])
async def trigger_job(
    job_id: int,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("datasets:write")),
) -> Result[TriggerEvalJobResult]:
    result = await service.trigger_job(session, job_id, triggered_by="manual")
    return Result.ok(result)


@router.get("/{job_id}/runs", response_model=Result[list[EvalJobRunItem]])
async def list_job_runs(
    job_id: int,
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("datasets:read")),
) -> Result[list[EvalJobRunItem]]:
    items = await service.list_job_runs(session, job_id, limit=limit)
    return Result.ok(items)
