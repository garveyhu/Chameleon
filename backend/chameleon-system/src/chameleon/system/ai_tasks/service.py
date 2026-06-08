"""ai_tasks 服务 —— 异步执行 + 状态跟踪 + 结果缓存。

执行机制：进程内 asyncio.create_task 后台跑（本地单实例够用）。task 引用挂在模块级 set 防
被 GC；进程重启用 recover_stale_tasks() 把残留 running/pending 标 failed 兜底。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import datetime, timezone

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.api.exceptions import BusinessError, ResultCode
from chameleon.data.infra.db import AsyncSessionLocal
from chameleon.data.models import AiTask
from chameleon.system.ai_tasks.registry import AI_TASK_HANDLERS
from chameleon.system.ai_tasks.schemas import AiTaskItem, SubmitAiTaskRequest

# 后台任务引用池：防 fire-and-forget 的 task 被 GC（asyncio 弱引用陷阱）。
_BG_TASKS: set[asyncio.Task] = set()


def _hash_input(task_type: str, payload: dict) -> str:
    canon = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(f"{task_type}\n{canon}".encode()).hexdigest()


def _spawn(coro) -> None:
    task = asyncio.create_task(coro)
    _BG_TASKS.add(task)
    task.add_done_callback(_BG_TASKS.discard)


async def submit_task(
    session: AsyncSession, req: SubmitAiTaskRequest, user_id: int | None = None
) -> AiTaskItem:
    """提交 AI 任务：命中缓存直接返已 success 任务，否则建 pending 并后台异步执行。"""
    if req.task_type not in AI_TASK_HANDLERS:
        raise BusinessError(
            ResultCode.Fail, message=f"未知 AI 任务类型: {req.task_type}"
        )
    input_hash = _hash_input(req.task_type, req.input)
    if not req.force:
        cached = (
            await session.execute(
                select(AiTask)
                .where(AiTask.input_hash == input_hash, AiTask.status == "success")
                .order_by(AiTask.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if cached is not None:
            return AiTaskItem.model_validate(cached)

    task = AiTask(
        task_type=req.task_type,
        scope=req.scope,
        scope_ref=req.scope_ref,
        input_hash=input_hash,
        input=req.input,
        status="pending",
        created_by=user_id,
    )
    session.add(task)
    await session.flush()
    await session.refresh(task)
    out = AiTaskItem.model_validate(task)
    task_id = task.id
    await session.commit()
    _spawn(_run_task(task_id))
    return out


async def _run_task(task_id: int) -> None:
    """后台执行单个任务（独立 session）；状态机 running → success/failed。"""
    async with AsyncSessionLocal() as s:
        task = (
            await s.execute(select(AiTask).where(AiTask.id == task_id))
        ).scalar_one_or_none()
        if task is None:
            return
        task.status = "running"
        task.started_at = datetime.now(timezone.utc)
        await s.commit()
        try:
            handler = AI_TASK_HANDLERS[task.task_type]
            result = await handler(s, task.input or {})
            task.status = "success"
            task.result = result
        except Exception as exc:  # noqa: BLE001 —— 统一兜底，错误入库
            logger.exception(
                "ai_task 执行失败 | id={} type={}", task_id, task.task_type
            )
            task.status = "failed"
            task.error = str(exc)[:1000]
        task.finished_at = datetime.now(timezone.utc)
        await s.commit()


async def get_task(session: AsyncSession, task_id: int) -> AiTaskItem:
    task = (
        await session.execute(select(AiTask).where(AiTask.id == task_id))
    ).scalar_one_or_none()
    if task is None:
        raise BusinessError(ResultCode.Fail, message=f"ai_task 不存在: {task_id}")
    return AiTaskItem.model_validate(task)


async def list_tasks(
    session: AsyncSession,
    *,
    scope: str | None = None,
    scope_ref: str | None = None,
    task_type: str | None = None,
    limit: int = 20,
) -> list[AiTaskItem]:
    """按业务归属列出历史任务（离开页面回来反显 / 缓存命中展示）。"""
    stmt = select(AiTask)
    if scope:
        stmt = stmt.where(AiTask.scope == scope)
    if scope_ref:
        stmt = stmt.where(AiTask.scope_ref == scope_ref)
    if task_type:
        stmt = stmt.where(AiTask.task_type == task_type)
    stmt = stmt.order_by(AiTask.id.desc()).limit(limit)
    rows = (await session.execute(stmt)).scalars().all()
    return [AiTaskItem.model_validate(r) for r in rows]


async def recover_stale_tasks() -> int:
    """启动钩子：残留 running/pending（进程重启中断）统一标 failed 兜底。"""
    async with AsyncSessionLocal() as s:
        rows = (
            await s.execute(
                select(AiTask).where(AiTask.status.in_(["running", "pending"]))
            )
        ).scalars().all()
        for t in rows:
            t.status = "failed"
            t.error = "进程重启，任务中断"
            t.finished_at = datetime.now(timezone.utc)
        await s.commit()
        return len(rows)
