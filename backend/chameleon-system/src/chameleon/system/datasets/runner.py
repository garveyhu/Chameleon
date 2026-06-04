"""DatasetRun 持久化运行器（P18.3 PR #25）

跑流程：
1. 建 DatasetRun（status=running）
2. 遍历 dataset_items：每条调 LLM（用 model_override / prompt_override）→ 拿 actual_output
3. judge(expected, actual) → score → 写一条 dataset_run_items + score 行
4. 终态 aggregate summary 写回 dataset_runs

scores 表打通：每 item 评分同时写 chameleon.data.models.Score 行（source='eval'）
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.api.exceptions import BusinessError, ResultCode
from chameleon.core.observe import (
    TraceContext,
    reset_trace_context,
    set_trace_context,
)
from chameleon.data.constants import Channel
from chameleon.data.models import (
    Dataset,
    DatasetItem,
    DatasetRun,
    DatasetRunItem,
    EvalTemplate,
    Score,
)
from chameleon.system.datasets.judges import JUDGES
from chameleon.system.datasets.template_scoring import score_run_with_template

EVAL_APP_ID = "__eval__"

_MAX_ITEMS_PER_RUN = 500  # 单次 run 上限


async def run_dataset(
    session: AsyncSession,
    *,
    dataset_id: int,
    name: str,
    model_override: str | None = None,
    prompt_override: str | None = None,
    judge: str = "exact_match",
    eval_template_id: int | None = None,
    agent_key: str | None = None,
) -> DatasetRun:
    """跑一次 dataset，持久化结果"""
    if judge not in JUDGES:
        raise BusinessError(
            ResultCode.Fail,
            message=f"未知 judge={judge!r}；可选: {sorted(JUDGES.keys())}",
        )

    ds = (
        await session.execute(select(Dataset).where(Dataset.id == dataset_id))
    ).scalar_one_or_none()
    if ds is None:
        raise BusinessError(ResultCode.Fail, message=f"dataset 不存在: {dataset_id}")

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
        agent_key=agent_key,
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
        # 评测流量进 Trace：每条 item 一个 request_id，绑定 channel='eval'，被测
        # LLM / agent 内部 LLM 的 generation 行都以此渠道盖章（参照 playground 写法）。
        request_id = uuid.uuid4().hex
        trace_token = set_trace_context(
            TraceContext(
                request_id=request_id,
                channel=Channel.EVAL.value,
                app_id=EVAL_APP_ID,
                agent_key=agent_key,
                session_id=f"eval-run-{run_id}",
            )
        )
        try:
            if agent_key:
                actual = await _invoke_via_agent(
                    agent_key, item.input_payload, request_id=request_id
                )
            else:
                actual = await _invoke_for_item(
                    item.input_payload,
                    model_override=model_override,
                    prompt_override=prompt_override,
                )
            if judge == "llm_judge":
                # AI 评分走 eval 渠道（在本 item 的 TraceContext scope 内），带理由
                score, reason = await _llm_judge_score(
                    item.expected_output, actual, model_override=model_override
                )
            else:
                score = await judge_fn(item.expected_output, actual)
                reason = None
            err = None
            ok_count += 1
        except Exception as e:  # noqa: BLE001
            actual = None
            score = None
            reason = None
            err = {"type": type(e).__name__, "message": str(e)[:300]}
            fail_count += 1
            logger.exception(
                "dataset run item failed | run={} | item={}", run_id, item.id
            )
        finally:
            reset_trace_context(trace_token)

        item_finished = datetime.now(timezone.utc)
        dur_ms = int((item_finished - item_started).total_seconds() * 1000)

        ri = DatasetRunItem(
            dataset_run_id=run_id,
            dataset_item_id=item.id,
            actual_output=_to_dict(actual),
            score=score,
            score_reason=reason,
            error=err,
            duration_ms=dur_ms,
        )
        session.add(ri)

        # mean_score 统计所有有分 item（含人工造样本，不依赖采样来源）
        if score is not None:
            score_sum += float(score)
            score_count += 1
            # Score 表回写仅对采样来源（有 call_log_id 锚点）的 item
            if item.source_call_log_id:
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

    run.status = "success" if fail_count == 0 else "failed"
    run.finished_at = datetime.now(timezone.utc)
    summary: dict[str, Any] = {
        "total": len(items),
        "ok": ok_count,
        "fail": fail_count,
        "mean_score": score_sum / score_count if score_count > 0 else None,
        "score_count": score_count,
    }

    # P21.2：可选 EvalTemplate 跑 RAGAS 多 metric 评分
    if eval_template_id is not None:
        template = (
            await session.execute(
                select(EvalTemplate).where(EvalTemplate.id == eval_template_id)
            )
        ).scalar_one_or_none()
        if template is not None:
            try:
                eval_summary = await score_run_with_template(
                    session, run_id=run_id, template=template
                )
                summary["eval_template"] = {
                    "id": template.id,
                    "name": template.name,
                    "version": template.version,
                    **eval_summary,
                }
            except Exception as e:  # noqa: BLE001
                logger.exception(
                    "eval template scoring failed | run={} | template={}",
                    run_id,
                    eval_template_id,
                )
                summary["eval_template_error"] = str(e)[:300]

    run.summary = summary
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
    from langchain_core.messages import HumanMessage, SystemMessage

    from chameleon.integrations.llms.factory import llm as get_llm

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


async def _llm_judge_score(
    expected: Any,
    actual: Any,
    *,
    model_override: str | None = None,
) -> tuple[float | None, str | None]:
    """LLM-as-judge：对比 期望/实际 输出 0-1 分 + 一句理由。

    在 run_dataset 的 channel='eval' TraceContext scope 内调用，judge LLM 调用
    自动盖 eval 渠道章（成本 / token 进 Trace）。expected 缺失则返 (None, None)。
    """
    from langchain_core.messages import HumanMessage

    from chameleon.integrations.llms.factory import llm as get_llm
    from chameleon.system.datasets.judges import _flatten_str

    exp = _flatten_str(expected).strip()
    act = _flatten_str(actual).strip()
    if not exp:
        return None, None

    prompt = (
        "你是严格的评测打分员。对比【期望答案】与【实际回答】的语义正确性与完整性，"
        "给一个 0 到 1 的小数分（1=完全正确，0=完全错误，可取中间值），"
        "并用一句话说明理由。\n\n"
        f"【期望答案】\n{exp}\n\n【实际回答】\n{act}\n\n"
        '只输出 JSON，不要多余文字：{"score": <0到1的小数>, "reason": "<一句话理由>"}'
    )
    client = get_llm(model_override)
    ai = await client.ainvoke([HumanMessage(content=prompt)])
    raw = ai.content if hasattr(ai, "content") else str(ai)
    return _parse_judge_json(str(raw))


def _parse_judge_json(raw: str) -> tuple[float | None, str | None]:
    """从 LLM 输出抽 {"score","reason"}，容错截取 JSON 段；失败则把原文当理由。"""
    import json
    import re

    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        return None, (raw.strip()[:300] or None)
    try:
        data = json.loads(m.group(0))
    except (ValueError, TypeError):
        return None, (raw.strip()[:300] or None)
    raw_score = data.get("score")
    raw_reason = data.get("reason")
    try:
        s = float(raw_score) if raw_score is not None else None
    except (ValueError, TypeError):
        s = None
    if s is not None:
        s = max(0.0, min(1.0, s))
    return s, (str(raw_reason)[:500] if raw_reason is not None else None)


async def _invoke_via_agent(
    agent_key: str,
    input_payload: dict[str, Any],
    *,
    request_id: str,
) -> dict[str, Any]:
    """A3：经 agent（含 graph 编排的）跑单条 —— 走统一 Provider 路径。

    把整个工作流 agent 当被测对象做回归打分；两个 agent / 两个版本各跑一次
    dataset，再用 compare_runs 做 A/B 胜率对比。

    `request_id` 由 run_dataset 外层连同 channel='eval' 的 TraceContext 一起 set；
    传进 InvokeContext 让 graph provider 的 merged_tc 沿用同一 request_id 与 eval
    渠道（provider 内部 LLM 节点的 generation 行随之盖章 channel='eval'）。
    """
    from chameleon.core.api.exceptions import BusinessError, ResultCode
    from chameleon.providers.base.registry import AGENTS, PROVIDERS
    from chameleon.providers.base.types import InvokeContext

    adef = AGENTS.get(agent_key)
    if adef is None:
        raise BusinessError(ResultCode.Fail, message=f"eval agent 未注册: {agent_key}")
    prov = PROVIDERS[adef.provider]
    query = _extract_query_text(input_payload)
    ctx = InvokeContext(
        agent_def=adef,
        input=query,
        session_id=f"eval-{agent_key}",
        app_id=EVAL_APP_ID,
        request_id=request_id,
        stream=False,
    )
    result = await prov.invoke(ctx)
    return {"answer": result.answer or ""}


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
