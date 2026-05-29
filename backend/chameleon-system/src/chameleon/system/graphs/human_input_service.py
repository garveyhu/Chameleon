"""human_input 断点查询 + 超时清扫（v1.1 PR A6）

- list_pending：列待回填断点（admin UI 用）
- sweep_timeouts：APScheduler 周期调用，把超时未回填的断点标 timeout 并把
  对应 graph_run 置 failed（防止 paused run 永久挂起）

回填恢复在 runner.resume_run（与 run_graph 同层）。
"""

from __future__ import annotations

from datetime import datetime, timezone

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.data.models import GraphRun, HumanInputPending
from chameleon.system.graphs.schemas import PendingInputItem


async def list_pending(
    session: AsyncSession, *, status: str = "pending", limit: int = 50
) -> list[PendingInputItem]:
    """列断点（默认 pending；可查 resolved / timeout）"""
    rows = (
        (
            await session.execute(
                select(HumanInputPending)
                .where(HumanInputPending.status == status)
                .order_by(HumanInputPending.created_at.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return [PendingInputItem.model_validate(r) for r in rows]


async def sweep_timeouts(session: AsyncSession) -> int:
    """把超时未回填的 pending 断点标 timeout，并 fail 其 graph_run

    返回处理条数。best-effort —— 单条异常不影响其余（由调用方 commit）。
    """
    now = datetime.now(timezone.utc)
    rows = (
        (
            await session.execute(
                select(HumanInputPending).where(
                    HumanInputPending.status == "pending",
                    HumanInputPending.timeout_at.is_not(None),
                    HumanInputPending.timeout_at < now,
                )
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        return 0

    for p in rows:
        p.status = "timeout"
        p.resolved_at = now
        run = (
            await session.execute(
                select(GraphRun).where(GraphRun.id == p.graph_run_id)
            )
        ).scalar_one_or_none()
        if run is not None and run.status == "paused":
            run.status = "failed"
            run.error = {
                "type": "HumanInputTimeout",
                "message": f"node {p.node_id} 等待人工回填超时",
            }
            run.finished_at = now
    await session.commit()
    logger.info("human_input sweep_timeouts | marked={}", len(rows))
    return len(rows)
