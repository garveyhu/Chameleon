"""ai_tasks API —— 提交 / 轮询 / 按业务归属列出 AI 任务。

POST /v1/admin/ai-tasks            提交（命中缓存直接返已 success 任务）
GET  /v1/admin/ai-tasks/{id}       轮询单个任务状态 + 结果
GET  /v1/admin/ai-tasks            按 scope/scope_ref/task_type 列历史（反显 / 缓存展示）
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.api.response import Result
from chameleon.data.infra.db import get_session
from chameleon.system.ai_tasks import service as ai_task_service
from chameleon.system.ai_tasks.schemas import AiTaskItem, SubmitAiTaskRequest
from chameleon.system.auth.dependencies import require_permission

router = APIRouter(prefix="/v1/admin/ai-tasks", tags=["admin:ai-tasks"])


@router.post("", response_model=Result[AiTaskItem])
async def submit_ai_task(
    req: SubmitAiTaskRequest,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("datasets:write")),
) -> Result[AiTaskItem]:
    """提交 AI 任务（异步后台执行；命中缓存直接复用已 success 任务）。"""
    item = await ai_task_service.submit_task(session, req)
    return Result.ok(item)


@router.get("/{task_id}", response_model=Result[AiTaskItem])
async def get_ai_task(
    task_id: int,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("datasets:read")),
) -> Result[AiTaskItem]:
    """轮询单个任务状态 + 结果。"""
    item = await ai_task_service.get_task(session, task_id)
    return Result.ok(item)


@router.get("", response_model=Result[list[AiTaskItem]])
async def list_ai_tasks(
    scope: str | None = Query(default=None),
    scope_ref: str | None = Query(default=None),
    task_type: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("datasets:read")),
) -> Result[list[AiTaskItem]]:
    """按业务归属列出历史任务（离开页面回来反显 / 缓存命中展示）。"""
    items = await ai_task_service.list_tasks(
        session,
        scope=scope,
        scope_ref=scope_ref,
        task_type=task_type,
        limit=limit,
    )
    return Result.ok(items)
