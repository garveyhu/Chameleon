"""eval_jobs 业务 service —— CRUD + 触发 + 与 scheduler 协作

调用关系：
- create / update / delete 后 invoke scheduler.sync_job() —— 由路由层串
- trigger 直接调 datasets.runner.run_dataset，把结果 link 进 eval_job_runs

red-line：cron_expr 强校验（用 APScheduler 的 CronTrigger 解析，避免半合法表达式）
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from apscheduler.triggers.cron import CronTrigger
from loguru import logger
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.api.exceptions import BusinessError, ResultCode
from chameleon.data.models import Dataset, EvalJob, EvalJobRun
from chameleon.system.datasets import runner as ds_runner
from chameleon.system.datasets.judges import JUDGES
from chameleon.system.eval_jobs.alert import maybe_send_alert
from chameleon.system.eval_jobs.schemas import (
    CreateEvalJobRequest,
    EvalJobItem,
    EvalJobRunItem,
    TriggerEvalJobResult,
    UpdateEvalJobRequest,
)

# ── CRUD ────────────────────────────────────────────────


async def list_jobs(session: AsyncSession) -> list[EvalJobItem]:
    rows = (
        (await session.execute(select(EvalJob).order_by(EvalJob.created_at.desc())))
        .scalars()
        .all()
    )
    return [EvalJobItem.model_validate(r) for r in rows]


async def get_job(session: AsyncSession, job_id: int) -> EvalJobItem:
    row = await _load_job(session, job_id)
    return EvalJobItem.model_validate(row)


async def create_job(
    session: AsyncSession, req: CreateEvalJobRequest
) -> EvalJobItem:
    await _validate_dataset(session, req.dataset_id)
    _validate_judge(req.judge)
    _validate_cron(req.cron_expr)
    await _validate_unique_key(session, req.job_key)

    row = EvalJob(
        job_key=req.job_key,
        name=req.name,
        description=req.description,
        dataset_id=req.dataset_id,
        target_kind=req.target_kind,
        target_key=req.target_key,
        model_override=req.model_override,
        prompt_override=req.prompt_override,
        judge=req.judge,
        cron_expr=req.cron_expr,
        alert_config=req.alert_config,
        enabled=req.enabled,
    )
    session.add(row)
    await session.flush()
    await session.refresh(row)
    item = EvalJobItem.model_validate(row)
    await session.commit()
    logger.info("eval_job created | id={} | key={}", row.id, row.job_key)
    return item


async def update_job(
    session: AsyncSession, job_id: int, req: UpdateEvalJobRequest
) -> EvalJobItem:
    row = await _load_job(session, job_id)
    if req.name is not None:
        row.name = req.name
    if req.description is not None:
        row.description = req.description
    if req.target_kind is not None:
        row.target_kind = req.target_kind
    if req.target_key is not None:
        row.target_key = req.target_key
    if req.model_override is not None:
        row.model_override = req.model_override
    if req.prompt_override is not None:
        row.prompt_override = req.prompt_override
    if req.judge is not None:
        _validate_judge(req.judge)
        row.judge = req.judge
    if req.cron_expr is not None:
        _validate_cron(req.cron_expr)
        row.cron_expr = req.cron_expr
    if req.alert_config is not None:
        row.alert_config = req.alert_config
    if req.enabled is not None:
        row.enabled = req.enabled
    await session.flush()
    await session.refresh(row)
    item = EvalJobItem.model_validate(row)
    await session.commit()
    return item


async def delete_job(session: AsyncSession, job_id: int) -> None:
    row = await _load_job(session, job_id)
    await session.execute(delete(EvalJob).where(EvalJob.id == row.id))
    await session.commit()


# ── trigger ─────────────────────────────────────────────


async def trigger_job(
    session: AsyncSession,
    job_id: int,
    *,
    triggered_by: str = "manual",
) -> TriggerEvalJobResult:
    """触发一次 eval job —— 同步跑 dataset_run + 写 eval_job_run

    PR #30：先同步执行；后续 PR 可改异步 task。
    """
    job = await _load_job(session, job_id)
    if not job.enabled:
        raise BusinessError(
            ResultCode.Fail, message=f"eval_job 已 disabled: {job.job_key}"
        )

    # 1) 先 commit 一行 pending 的 eval_job_run（让它独立于 dataset_run 事务，确保失败时也有痕迹）
    started_at = datetime.now(timezone.utc)
    job_run = EvalJobRun(
        job_id=job.id,
        triggered_by=triggered_by,
        status="running",
        created_at=started_at,
    )
    session.add(job_run)
    await session.flush()
    await session.refresh(job_run)
    jr_id = job_run.id
    await session.commit()

    # 2) 跑 dataset_run（复用 datasets.runner，内部会再 commit 一次）
    try:
        dataset_run = await ds_runner.run_dataset(
            session,
            dataset_id=job.dataset_id,
            name=f"eval-job:{job.job_key}@{started_at.isoformat()[:19]}",
            model_override=job.model_override,
            prompt_override=job.prompt_override,
            judge=job.judge,
        )
        mean_score = _to_decimal(
            (dataset_run.summary or {}).get("mean_score") if dataset_run.summary else None
        )
        prev = _to_decimal(job.last_score)
        delta = (
            (mean_score - prev) if (mean_score is not None and prev is not None) else None
        )
        # ds_runner.run_dataset 已 commit；这里重新 attach
        job_run = await session.get(EvalJobRun, jr_id)
        assert job_run is not None
        job_run.dataset_run_id = dataset_run.id
        job_run.mean_score = mean_score
        job_run.delta_score = delta
        job_run.status = dataset_run.status
        job_run.finished_at = datetime.now(timezone.utc)

        # 同步 job 主表的 last_*
        job = await session.get(EvalJob, job.id)
        assert job is not None
        job.last_run_at = job_run.finished_at
        if mean_score is not None:
            job.last_score = mean_score
        await session.commit()
        await session.refresh(job_run)

        # alert pipeline：失败不能污染主路径
        try:
            await maybe_send_alert(session, job, job_run)
        except Exception:  # noqa: BLE001
            logger.exception(
                "eval_alert pipeline raised | job={}", job.id
            )
    except Exception as e:  # noqa: BLE001
        logger.exception("eval_job trigger failed | id={}", job_id)
        # 回滚后只更新失败状态
        await session.rollback()
        job_run = await session.get(EvalJobRun, jr_id)
        if job_run is not None:
            job_run.status = "failed"
            job_run.error = {"type": type(e).__name__, "message": str(e)[:300]}
            job_run.finished_at = datetime.now(timezone.utc)
            await session.commit()
        raise

    return TriggerEvalJobResult(
        job_run_id=jr_id,
        dataset_run_id=job_run.dataset_run_id,
        status=job_run.status,
        mean_score=job_run.mean_score,
    )


# ── job_runs 查询 ───────────────────────────────────────


async def list_job_runs(
    session: AsyncSession, job_id: int, *, limit: int = 50
) -> list[EvalJobRunItem]:
    rows = (
        (
            await session.execute(
                select(EvalJobRun)
                .where(EvalJobRun.job_id == job_id)
                .order_by(EvalJobRun.created_at.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return [EvalJobRunItem.model_validate(r) for r in rows]


# ── helpers ─────────────────────────────────────────────


async def _load_job(session: AsyncSession, job_id: int) -> EvalJob:
    row = (
        await session.execute(select(EvalJob).where(EvalJob.id == job_id))
    ).scalar_one_or_none()
    if row is None:
        raise BusinessError(
            ResultCode.NotFound, message=f"eval_job 不存在: {job_id}"
        )
    return row


async def _validate_dataset(session: AsyncSession, dataset_id: int) -> None:
    exists = (
        await session.execute(
            select(Dataset.id).where(Dataset.id == dataset_id)
        )
    ).scalar_one_or_none()
    if exists is None:
        raise BusinessError(
            ResultCode.Fail, message=f"dataset 不存在: {dataset_id}"
        )


async def _validate_unique_key(session: AsyncSession, job_key: str) -> None:
    exists = (
        await session.execute(
            select(EvalJob.id).where(EvalJob.job_key == job_key)
        )
    ).scalar_one_or_none()
    if exists is not None:
        raise BusinessError(
            ResultCode.Fail, message=f"job_key 已存在: {job_key}"
        )


def _validate_judge(judge: str) -> None:
    if judge not in JUDGES:
        raise BusinessError(
            ResultCode.Fail,
            message=f"未知 judge={judge!r}；可选: {sorted(JUDGES.keys())}",
        )


def _validate_cron(cron_expr: str) -> None:
    try:
        CronTrigger.from_crontab(cron_expr)
    except Exception as e:
        raise BusinessError(
            ResultCode.Fail,
            message=f"非法 cron_expr={cron_expr!r}: {e}",
        )


def _to_decimal(v: Any) -> Decimal | None:
    if v is None:
        return None
    try:
        return Decimal(str(v)).quantize(Decimal("0.0001"))
    except Exception:
        return None
