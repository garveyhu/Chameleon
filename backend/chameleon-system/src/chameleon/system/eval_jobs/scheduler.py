"""APScheduler 集成 —— eval_jobs cron 触发

设计：
- AsyncIOScheduler 单例，由 lifespan startup 起；shutdown 时优雅停
- jobstore = MemoryJobStore（默认）；启动时从 DB 重建 enabled job 列表
- CRUD 后路由层调 sync_job(id) / remove_job(id) 同步 scheduler 状态
- 触发回调（_run_job_callback）自己开新 db session，不复用请求 session

红线（plan §2 新增）：
- 全 async，不阻塞主事件循环
- 单次回调失败不能拖垮 scheduler —— 内部捕获 + log
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger
from sqlalchemy import select

from chameleon.core.infra.db import AsyncSessionLocal
from chameleon.core.models import EvalJob

if TYPE_CHECKING:
    pass


_scheduler: AsyncIOScheduler | None = None


def _job_apscheduler_id(job_id: int) -> str:
    return f"eval-job-{job_id}"


async def start() -> None:
    """lifespan startup：起 scheduler + 重载所有 enabled jobs"""
    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = AsyncIOScheduler()
    _scheduler.start()
    logger.info("eval_jobs scheduler started")

    async with AsyncSessionLocal() as session:
        rows = (
            (await session.execute(select(EvalJob).where(EvalJob.enabled.is_(True))))
            .scalars()
            .all()
        )
        for row in rows:
            _register(row.id, row.cron_expr)
    logger.info("eval_jobs scheduler reloaded {} jobs", len(rows))


async def shutdown() -> None:
    global _scheduler
    if _scheduler is None:
        return
    _scheduler.shutdown(wait=False)
    _scheduler = None
    logger.info("eval_jobs scheduler stopped")


async def sync_job(job_id: int) -> None:
    """create/update 后调：按 DB 状态重注册（enabled=False 则移除）"""
    if _scheduler is None:
        return  # 测试环境 / scheduler 未起，跳过
    async with AsyncSessionLocal() as session:
        row = (
            await session.execute(select(EvalJob).where(EvalJob.id == job_id))
        ).scalar_one_or_none()
        if row is None or not row.enabled:
            remove_job(job_id)
            return
        _register(row.id, row.cron_expr)


def remove_job(job_id: int) -> None:
    if _scheduler is None:
        return
    apsched_id = _job_apscheduler_id(job_id)
    try:
        _scheduler.remove_job(apsched_id)
    except Exception:
        # 可能本来就没注册（disabled 直接 delete），忽略
        pass


def _register(job_id: int, cron_expr: str) -> None:
    """添加 / 覆盖一个 cron 触发的 eval job"""
    assert _scheduler is not None
    apsched_id = _job_apscheduler_id(job_id)
    try:
        trigger = CronTrigger.from_crontab(cron_expr)
    except Exception as e:
        logger.warning(
            "eval_jobs scheduler skip job {} | bad cron={} | {}",
            job_id,
            cron_expr,
            e,
        )
        return
    _scheduler.add_job(
        _run_job_callback,
        trigger=trigger,
        id=apsched_id,
        args=[job_id],
        replace_existing=True,
        misfire_grace_time=300,
        coalesce=True,
        max_instances=1,
    )


async def _run_job_callback(job_id: int) -> None:
    """cron 触发的回调 —— 自管 session，自捕获异常"""
    from chameleon.system.eval_jobs import service  # 延迟导入避免循环

    logger.info("eval_jobs cron fired | job_id={}", job_id)
    async with AsyncSessionLocal() as session:
        try:
            await service.trigger_job(session, job_id, triggered_by="cron")
        except Exception:
            logger.exception("eval_jobs cron callback failed | job_id={}", job_id)
