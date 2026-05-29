"""EvalTemplate 跑分集成 —— P21.2 PR #64

跑 dataset_run 后调 score_run_with_template() 遍历 items 按 template metrics
评分；多 metric 加权得 weighted_total。

红线：
- builtin 算子注册表只读；用户改 weight 走 EvalTemplate.metrics 配置
- 评分失败的 item 不阻塞 run；error 记录到 eval_scores._error
"""

from __future__ import annotations

from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.data.models import (
    DatasetItem,
    DatasetRunItem,
    EvalTemplate,
)
from chameleon.engine.eval import get_algorithm


async def score_run_with_template(
    session: AsyncSession,
    *,
    run_id: int,
    template: EvalTemplate,
) -> dict[str, Any]:
    """遍历 run_items，按 template.metrics 评分并写回 eval_scores

    Returns:
        汇总：{ "metric_name": mean_score, ..., "weighted_total_mean": float, "scored_items": N }
    """
    rows = (
        (
            await session.execute(
                select(DatasetRunItem, DatasetItem)
                .join(
                    DatasetItem,
                    DatasetItem.id == DatasetRunItem.dataset_item_id,
                )
                .where(DatasetRunItem.dataset_run_id == run_id)
            )
        )
        .all()
    )

    metrics_cfg = template.metrics or []
    if not metrics_cfg:
        return {"scored_items": 0, "weighted_total_mean": None}

    total_weight = sum(float(m.get("weight", 0.0)) for m in metrics_cfg) or 1.0

    per_metric_sums: dict[str, float] = {}
    per_metric_counts: dict[str, int] = {}
    weighted_totals: list[float] = []

    for run_item, ds_item in rows:
        if run_item.error is not None:
            continue
        question, answer, contexts, ground_truth = _extract_eval_inputs(
            ds_item, run_item
        )
        scores: dict[str, float] = {}
        for m in metrics_cfg:
            algo_key = str(m.get("algorithm") or "")
            algo = get_algorithm(algo_key)
            metric_name = str(m.get("name") or algo_key)
            if algo is None:
                scores[metric_name] = 0.0
                logger.warning(
                    "ragas algorithm not registered: {} (run_item={})",
                    algo_key,
                    run_item.id,
                )
                continue
            try:
                s = await algo(
                    question=question,
                    answer=answer,
                    contexts=contexts,
                    ground_truth=ground_truth,
                    config=m.get("config"),
                    judge_fn=None,
                )
            except Exception as e:  # noqa: BLE001
                logger.exception(
                    "eval algorithm failed | algo={} | run_item={}",
                    algo_key,
                    run_item.id,
                )
                scores["_error"] = str(e)[:200]
                continue
            scores[metric_name] = float(s)
            per_metric_sums[metric_name] = (
                per_metric_sums.get(metric_name, 0.0) + float(s)
            )
            per_metric_counts[metric_name] = (
                per_metric_counts.get(metric_name, 0) + 1
            )

        weighted = sum(
            scores.get(str(m.get("name") or m.get("algorithm")), 0.0)
            * float(m.get("weight", 0.0))
            for m in metrics_cfg
        )
        weighted_total = weighted / total_weight
        scores["weighted_total"] = weighted_total
        weighted_totals.append(weighted_total)
        run_item.eval_scores = scores

    await session.flush()

    summary: dict[str, Any] = {
        m: (
            per_metric_sums[m] / per_metric_counts[m]
            if per_metric_counts.get(m, 0) > 0
            else None
        )
        for m in per_metric_sums
    }
    summary["weighted_total_mean"] = (
        sum(weighted_totals) / len(weighted_totals)
        if weighted_totals
        else None
    )
    summary["scored_items"] = len(weighted_totals)
    return summary


def _extract_eval_inputs(
    ds_item: DatasetItem, run_item: DatasetRunItem
) -> tuple[str, str, list[str], str | None]:
    """从 DatasetItem + RunItem 抽 (question, answer, contexts, ground_truth)

    脱敏后 input_payload 用 preview 字段当 question。
    """
    question = _extract_preview_text(ds_item.input_payload or {})
    answer = _extract_answer_text(run_item.actual_output or {})
    contexts = _extract_contexts(run_item.actual_output or {})
    ground_truth = _extract_ground_truth(ds_item.expected_output)
    return question, answer, contexts, ground_truth


def _extract_preview_text(payload: dict[str, Any]) -> str:
    for k in ("user_input", "query", "question", "input", "text"):
        v = payload.get(k)
        if isinstance(v, dict) and isinstance(v.get("preview"), str):
            return v["preview"]
        if isinstance(v, str):
            return v
    return ""


def _extract_answer_text(actual: dict[str, Any]) -> str:
    for k in ("answer", "text", "content", "output"):
        v = actual.get(k)
        if isinstance(v, str):
            return v
    return ""


def _extract_contexts(actual: dict[str, Any]) -> list[str]:
    cites = actual.get("citations") or actual.get("contexts") or []
    out: list[str] = []
    if isinstance(cites, list):
        for c in cites:
            if isinstance(c, str):
                out.append(c)
            elif isinstance(c, dict):
                for k in ("content", "snippet", "text"):
                    if isinstance(c.get(k), str):
                        out.append(c[k])
                        break
    return out


def _extract_ground_truth(expected: dict[str, Any] | None) -> str | None:
    if not expected or not isinstance(expected, dict):
        return None
    for k in ("answer", "text", "content", "ground_truth", "expected"):
        v = expected.get(k)
        if isinstance(v, str):
            return v
    return None
