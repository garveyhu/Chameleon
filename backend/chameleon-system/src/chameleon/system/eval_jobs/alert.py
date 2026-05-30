"""Eval alert 触发管线 —— P19.1 PR #31

Pipeline：trigger_job 跑完 → maybe_send_alert(job, job_run)
  1. alert_config 缺 / 没配 kind → no-op
  2. delta_score 未触发 threshold → no-op
  3. Redis SET NX EX(silence_minutes) → 拿不到锁说明在静默期 → no-op + log
  4. 调 NOTIFIER_REGISTRY[kind].send() → 成功则把 eval_job_run.alert_sent / alert_target 持久化

红线（plan §2）：
- 同一 (job_id, kind) 静默期 1h（默认）—— 防风暴
- alert 失败不抛错，只 log；不能因为 alert 故障污染主 trigger 路径
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.data.infra import redis as redis_infra
from chameleon.data.models import EvalJob, EvalJobRun
from chameleon.integrations.components.notifier import get_notifier

_DEFAULT_THRESHOLD = Decimal("0.0")  # 不配则不触发
_DEFAULT_SILENCE_SEC = 3600  # 1 小时


def should_alert(alert_config: dict[str, Any] | None, delta_score: Decimal | None) -> bool:
    """阈值判定：delta_score 跌幅 >= threshold 触发"""
    if not isinstance(alert_config, dict) or not alert_config.get("kind"):
        return False
    if delta_score is None:
        return False
    threshold = _to_decimal(alert_config.get("regression_threshold"))
    if threshold is None or threshold <= 0:
        return False
    # delta_score < 0 = 下跌；abs(delta) >= threshold 触发
    return delta_score <= -threshold


async def maybe_send_alert(
    session: AsyncSession,
    job: EvalJob,
    job_run: EvalJobRun,
) -> bool:
    """完整 alert 管线；返 True 表示已发出（含静默期内为 False）"""
    cfg = job.alert_config
    if not should_alert(cfg, job_run.delta_score):
        return False

    assert isinstance(cfg, dict)
    kind = cfg["kind"]
    target = cfg.get("target")
    if not isinstance(target, str) or not target:
        logger.warning(
            "eval_alert misconfigured | job={} | kind={} | empty target",
            job.id,
            kind,
        )
        return False

    # Redis dedup —— SET NX 拿不到就静默
    silence_sec = _silence_seconds(cfg)
    key = f"eval_alert:{job.id}:{kind}"
    try:
        acquired = await redis_infra.get_redis().set(
            key, "1", nx=True, ex=silence_sec
        )
    except Exception as e:
        logger.warning(
            "eval_alert redis error | job={} | err={}", job.id, e
        )
        acquired = True  # Redis 挂了不能拖垮告警；fail-open
    if not acquired:
        logger.info(
            "eval_alert deduped | job={} | kind={} | within silence {}s",
            job.id,
            kind,
            silence_sec,
        )
        return False

    notifier = get_notifier(kind)
    if notifier is None:
        logger.warning("eval_alert unknown kind | job={} | kind={}", job.id, kind)
        return False

    text = _format_text(job, job_run)
    payload = _format_payload(job, job_run)
    try:
        sent = await notifier.send(target, text=text, payload=payload)
    except Exception:  # noqa: BLE001
        logger.exception("eval_alert notifier raised | job={}", job.id)
        sent = False

    if sent:
        job_run.alert_sent = True
        job_run.alert_target = target[:255]
        await session.commit()
        logger.info(
            "eval_alert sent | job={} | kind={} | delta={}",
            job.id,
            kind,
            job_run.delta_score,
        )
    return sent


# ── helpers ─────────────────────────────────────────────


def _silence_seconds(cfg: dict[str, Any]) -> int:
    minutes = cfg.get("silence_minutes")
    if isinstance(minutes, (int, float)) and minutes > 0:
        return int(minutes * 60)
    return _DEFAULT_SILENCE_SEC


def _format_text(job: EvalJob, run: EvalJobRun) -> str:
    delta_pct = (
        f"{float(run.delta_score) * 100:+.2f}%"
        if run.delta_score is not None
        else "n/a"
    )
    score = f"{float(run.mean_score):.4f}" if run.mean_score is not None else "n/a"
    return (
        f":rotating_light: Eval regression on `{job.job_key}` ({job.name})\n"
        f"• mean_score = {score}\n"
        f"• delta = {delta_pct}\n"
        f"• judge = {job.judge}\n"
        f"• run id = {run.id}"
    )


def _format_payload(job: EvalJob, run: EvalJobRun) -> dict[str, Any]:
    return {
        "job_id": job.id,
        "job_key": job.job_key,
        "job_run_id": run.id,
        "dataset_run_id": run.dataset_run_id,
        "mean_score": _to_float(run.mean_score),
        "delta_score": _to_float(run.delta_score),
        "judge": job.judge,
        "triggered_by": run.triggered_by,
    }


def _to_decimal(v: Any) -> Decimal | None:
    if v is None:
        return None
    try:
        return Decimal(str(v))
    except Exception:
        return None


def _to_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except Exception:
        return None
