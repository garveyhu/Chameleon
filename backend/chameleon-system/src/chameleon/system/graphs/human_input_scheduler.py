"""human_input 断点超时清扫 cron（v1.1 PR A6）

AsyncIOScheduler 单例，lifespan startup 起：每 5 分钟扫一遍超时未回填的断点，
标 timeout 并 fail 对应 paused run。回调自管 session、自捕获异常，单次失败不拖垮。
"""

from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from loguru import logger

from chameleon.core.infra.db import AsyncSessionLocal

_scheduler: AsyncIOScheduler | None = None
_SWEEP_INTERVAL_MIN = 5


async def start() -> None:
    """lifespan startup：起 scheduler + 注册超时清扫 job"""
    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = AsyncIOScheduler()
    _scheduler.start()
    _scheduler.add_job(
        _sweep_callback,
        trigger=IntervalTrigger(minutes=_SWEEP_INTERVAL_MIN),
        id="human-input-timeout-sweep",
        replace_existing=True,
        misfire_grace_time=300,
        coalesce=True,
        max_instances=1,
    )
    logger.info(
        "human_input timeout scheduler started (every {}min)", _SWEEP_INTERVAL_MIN
    )


async def shutdown() -> None:
    global _scheduler
    if _scheduler is None:
        return
    _scheduler.shutdown(wait=False)
    _scheduler = None
    logger.info("human_input timeout scheduler stopped")


async def _sweep_callback() -> None:
    from chameleon.system.graphs import human_input_service

    async with AsyncSessionLocal() as session:
        try:
            await human_input_service.sweep_timeouts(session)
        except Exception:
            logger.exception("human_input timeout sweep failed")
