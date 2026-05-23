"""DatasetRun 持久化运行器（P18.3 PR #25）

跑流程：
1. 建 DatasetRun（status=running）
2. 遍历 dataset_items：每条调 LLM（用 model_override / prompt_override）→ 拿 actual_output
3. judge(expected, actual) → score → 写一条 dataset_run_items + score 行
4. 终态 aggregate summary 写回 dataset_runs

scores 表打通：每 item 评分同时写 chameleon.core.models.Score 行（source='eval'）
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.api.exceptions import BusinessError, ResultCode
from chameleon.core.models import (
    Dataset,
    DatasetItem,
    DatasetRun,
    DatasetRunItem,
    Score,
)
from chameleon.system.datasets.judges import JUDGES


_MAX_ITEMS_PER_RUN = 500  # 单次 run 上限


async def run_dataset(
    session: AsyncSession,
    *,
    dataset_id: int,
    name: str,
    model_override: str | None = None,
    prompt_override: str | None = None,
    judge: str = "exact_match",
) -> DatasetRun:
    """跑一次 dataset，持久化结果"""
    if judge not in JUDGES:
        raise BusinessError(
            ResultCode.Fail,
            message=f"未知 judge={judge!r}；可选: {sorted(JUDGES.keys())}",
        )

    ds = (
        await session.execute(
            select(Dataset).where(Dataset.id == dataset_id)
        )
    ).scalar_one_or_none()
    if ds is None:
        raise BusinessError(
            ResultCode.Fail, message=f"dataset 不存在: {dataset_id}"
        )

    items = (
        (
            await session.execute(
                select(DatasetItem)
                .where(DatasetItem.dataset_id == dataset_id)
                .limit(_MAX_ITEMS_PER_RUN)
            )
        )
        .scalars()
        .all()
    )
    if not items:
        raise BusinessError(
            ResultCode.Fail,
            message=f"dataset {dataset_id} 没有 items；先采样再 run",
        )

    started_at = datetime.now(timezone.utc)
    run = DatasetRun(
        dataset_id=ds.id,
        name=name,
        model_override=model_override,
        prompt_override=prompt_override,
        judge=judge,
        status="running",
        started_at=started_at,
    )
    session.add(run)
    await session.flush()
    await session.refresh(run)
    run_id = run.id

    judge_fn = JUDGES[judge]
    ok_count = 0
    fail_count = 0
    score_sum = 0.0
    score_count = 0

    for item in items:
        item_started = datetime.now(timezone.utc)
        try:
            actual = await _invoke_for_item(
                item.input_payload,
                model_override=model_override,
                prompt_override=prompt_override,
            )
            score = await judge_fn(item.expected_output, actual)
            err = None
            ok_count += 1
        except Exception as e:  # noqa: BLE001
            actual = None
            score = None
            err = {"type": type(e).__name__, "message": str(e)[:300]}
            fail_count += 1
            logger.exception(
                "dataset run item failed | run={} | item={}", run_id, item.id
            )

        item_finished = datetime.now(timezone.utc)
        dur_ms = int((item_finished - item_started).total_seconds() * 1000)

        ri = DatasetRunItem(
            dataset_run_id=run_id,
            dataset_item_id=item.id,
            actual_output=_to_dict(actual),
            score=score,
            error=err,
            duration_ms=dur_ms,
        )
        session.add(ri)

        # scores 表打通：source='eval'，trace_id 借用 dataset_item.source_call_log_id
        if score is not None and item.source_call_log_id:
            session.add(
                Score(
                    call_log_id=item.source_call_log_id,
                    trace_id=item.source_call_log_id,
                    name=f"dataset_run:{judge}",
                    value=float(score),
                    data_type="numeric",
                    source="eval",
                    comment=f"dataset_run_id={run_id}",
                )
            )
            score_sum += float(score)
            score_count += 1

    run.status = "success" if fail_count == 0 else "failed"
    run.finished_at = datetime.now(timezone.utc)
    run.summary = {
        "total": len(items),
        "ok": ok_count,
        "fail": fail_count,
        "mean_score": score_sum / score_count if score_count > 0 else None,
        "score_count": score_count,
    }
    await session.commit()
    await session.refresh(run)

    logger.info(
        "dataset run | id={} | ds={} | judge={} | ok={}/{} | mean_score={}",
        run_id,
        ds.id,
        judge,
        ok_count,
        len(items),
        run.summary["mean_score"],
    )
    return run


async def _invoke_for_item(
    input_payload: dict[str, Any],
    *,
    model_override: str | None,
    prompt_override: str | None,
) -> dict[str, Any]:
    """跑单条 invoke：调 LLM 用 preview 字段当 user query

    脱敏后 input_payload 没有原文（只有 preview），P18 暂用 preview 跑；
    需要原文的场景靠 admin 在 dataset_items 上人工补 expected_output 然后 LLM 跑回测。
    """
    from chameleon.core.components.llms.factory import llm as get_llm
    from langchain_core.messages import HumanMessage, SystemMessage

    # 从 input_payload 提 query（脱敏后字段 preview / user_input.preview）
    query = _extract_query_text(input_payload)
    msgs: list = []
    if prompt_override:
        msgs.append(SystemMessage(content=prompt_override))
    msgs.append(HumanMessage(content=query))

    client = get_llm(model_override)
    ai = await client.ainvoke(msgs)
    content = ai.content if hasattr(ai, "content") else str(ai)
    return {"answer": content}


def _extract_query_text(input_payload: dict[str, Any]) -> str:
    """从脱敏 input_payload 提 text：优先 preview，fallback 拼字段名"""
    if not isinstance(input_payload, dict):
        return str(input_payload)
    for k in ("user_input", "query", "question", "input", "text"):
        v = input_payload.get(k)
        if isinstance(v, dict) and isinstance(v.get("preview"), str):
            return v["preview"]
        if isinstance(v, str):
            return v
    # fallback：返回字段名摘要
    return f"[redacted dataset item; keys={list(input_payload.keys())}]"


def _to_dict(v: Any) -> dict[str, Any] | None:
    if v is None:
        return None
    if isinstance(v, dict):
        return v
    return {"value": v}
