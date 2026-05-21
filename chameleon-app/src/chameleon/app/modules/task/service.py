"""task 业务服务"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.app.modules.task.schemas import TaskItem
from chameleon.core.infra.auth import CurrentApp
from chameleon.core.api.exceptions import TaskNotFoundError
from chameleon.core.models import Task


async def get_task(
    session: AsyncSession,
    task_id: int,
    *,
    current_app: CurrentApp | None = None,
) -> TaskItem:
    row = (
        await session.execute(select(Task).where(Task.id == task_id))
    ).scalar_one_or_none()
    if row is None:
        raise TaskNotFoundError(message=f"任务不存在: {task_id}")

    # 普通 app 仅看自己投递的；admin 看全量
    if current_app is not None and "admin" not in current_app.scopes:
        if row.app_id is not None and row.app_id != current_app.app_id:
            raise TaskNotFoundError(message=f"任务不存在: {task_id}")

    return TaskItem.model_validate(row)


# ── worker 端用 helpers（不暴露给 HTTP） ─────────────────


async def mark_running(session: AsyncSession, task_id: int) -> None:
    row = await _take(session, task_id)
    row.status = "running"
    row.started_at = datetime.now(timezone.utc)
    await session.flush()


async def mark_progress(
    session: AsyncSession, task_id: int, progress: int, message: str | None = None
) -> None:
    row = await _take(session, task_id)
    row.progress = max(0, min(100, int(progress)))
    if message is not None:
        row.message = message
    await session.flush()


async def mark_success(
    session: AsyncSession, task_id: int, result: dict | None = None
) -> None:
    row = await _take(session, task_id)
    row.status = "success"
    row.progress = 100
    row.result = result
    row.finished_at = datetime.now(timezone.utc)
    await session.flush()


async def mark_failed(session: AsyncSession, task_id: int, error: dict) -> None:
    row = await _take(session, task_id)
    row.status = "failed"
    row.error = error
    row.finished_at = datetime.now(timezone.utc)
    await session.flush()


async def _take(session: AsyncSession, task_id: int) -> Task:
    row = (
        await session.execute(select(Task).where(Task.id == task_id))
    ).scalar_one_or_none()
    if row is None:
        raise TaskNotFoundError(message=f"任务不存在: {task_id}")
    return row
