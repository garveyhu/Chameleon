"""DatasetRun 持久化运行器（P18.3 PR #25）

跑流程：
1. 建 DatasetRun（status=running）
2. 遍历 dataset_items：每条调 LLM（用 model_override / prompt_override）→ 拿 actual_output
3. run_judge(judge, expected, actual, reference, config) → JudgeResult → 写一条
   dataset_run_items（score / score_reason / field_scores / reference_output）+ score 行
4. 终态 aggregate summary 写回 dataset_runs

评分契约（模块 G）：统一走 run_judge 分发器返 JudgeResult（score 恒 [0,1]）。需 LLM 的
judge（llm_judge / llm_score / gsb）在 channel='eval' TraceContext scope 内调 LLM；
旧窄函数（exact_match / contains）经 _as_judge_result 适配；dsl 走 datasets.dsl
解析器（parse → evaluate，NL 规则复用同一 eval 渠道 LLM）。

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
from chameleon.system.api_key.service import (
    aggregate_generation_rollup,
    record_call,
)
from chameleon.system.datasets.judges import (
    JUDGES,
    LLM_JUDGES,
    JudgeResult,
    build_gsb_prompt,
    build_llm_score_prompt,
    parse_gsb_result,
    parse_score_result,
)
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
    judge_config: dict[str, Any] | None = None,
    eval_template_id: int | None = None,
    agent_key: str | None = None,
    api_key_id: int | None = None,
) -> DatasetRun:
    """跑一次 dataset，持久化结果。

    api_key_id：可选「归属 Key」。评测本是后台内部流量、不经 API Key，但用户常希望把
    评测的 token/成本/trace 计到某个专用 Key 名下单独统计——传入则写进每条 item 的
    TraceContext + eval 根行，Trace 列表据此 join 出真实 Key 名。
    """
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
                api_key_id=api_key_id,
                session_id=f"eval-run-{run_id}",
            )
        )
        item_ok = True
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
            # 统一走分发器：需 LLM 的 judge 在本 item 的 channel='eval' TraceContext
            # scope 内调 LLM（成本/token 自动盖 eval 渠道章），否则旧函数 + 适配器。
            result = await run_judge(
                judge,
                item.expected_output,
                actual,
                reference=item.reference_output,
                config=judge_config,
                model_override=model_override,
            )
            score = result.score
            reason = result.reason
            field_scores = result.field_scores
            err = None
            ok_count += 1
        except Exception as e:  # noqa: BLE001
            actual = None
            score = None
            reason = None
            field_scores = None
            err = {"type": type(e).__name__, "message": str(e)[:300]}
            item_ok = False
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
            request_id=request_id,
            actual_output=_to_dict(actual),
            score=score,
            score_reason=reason,
            field_scores=field_scores,
            reference_output=item.reference_output if judge == "gsb" else None,
            error=err,
            duration_ms=dur_ms,
        )
        session.add(ri)

        # 评测流量进 Trace 列表：补写 eval 根 trace 行（trace 列表只列 parent_id IS
        # NULL 的根，缺它则被测 / judge 的 generation 子行无根可挂、列表里完全看不到）。
        # token/cost/model 从本 item 的 generation 子行 SUM 回灌（参照 playground 根行）。
        await _record_eval_trace_root(
            session,
            request_id=request_id,
            run_id=run_id,
            agent_key=agent_key,
            api_key_id=api_key_id,
            success=item_ok,
            duration_ms=dur_ms,
            input_payload=item.input_payload,
            actual=actual,
            error=err,
        )

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


async def _record_eval_trace_root(
    session: AsyncSession,
    *,
    request_id: str,
    run_id: int,
    agent_key: str | None,
    api_key_id: int | None,
    success: bool,
    duration_ms: int,
    input_payload: dict[str, Any],
    actual: dict[str, Any] | None,
    error: dict[str, Any] | None,
) -> None:
    """补写 eval 根 trace 行（observation_type='trace'，parent_id=NULL）。

    评测 LLM / 被测 agent 的 generation·embedding·retriever 子观测都挂在本 item 的
    request_id 下，但此前没有任何入口为该 request_id 落根行——导致 Trace 列表
    （只列 parent_id IS NULL 的根）完全看不到 eval 流量。这里 SUM 子 generation 的
    token/cost/model 回灌根行，使评测在 Trace 页可筛、可看、列不为空。
    """
    try:
        p, c, t, cost, model = await aggregate_generation_rollup(session, request_id)
        answer = ""
        if isinstance(actual, dict):
            answer = str(actual.get("answer") or actual.get("value") or "")
        await record_call(
            session,
            request_id=request_id,
            app_id=EVAL_APP_ID,
            agent_key=agent_key or "eval",
            api_key_id=api_key_id,
            session_id=f"eval-run-{run_id}",
            channel=Channel.EVAL.value,
            stream=False,
            success=success,
            code=0 if success else 500,
            error_message=(error or {}).get("message") if error else None,
            duration_ms=duration_ms,
            prompt_tokens=p,
            completion_tokens=c,
            total_tokens=t,
            request_payload={"question": _extract_query_text(input_payload)[:1000]},
            response_payload={"output": answer[:4000]} if answer else None,
            observation_type="trace",
            model_code=model,
            cost_usd=cost,
        )
    except Exception:  # noqa: BLE001
        logger.exception(
            "eval trace root record failed | run={} | rid={}", run_id, request_id
        )


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


def _as_judge_result(raw: float | JudgeResult | None) -> JudgeResult:
    """把旧窄签名 judge（返 float | None）适配成 JudgeResult。

    float → JudgeResult(score=raw)；JudgeResult → 透传；None → score=None。
    """
    if isinstance(raw, JudgeResult):
        return raw
    if raw is None:
        return JudgeResult(score=None)
    return JudgeResult(score=float(raw))


async def run_judge(
    judge_key: str,
    expected: Any,
    actual: Any,
    *,
    reference: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
    model_override: str | None = None,
) -> JudgeResult:
    """评分分发器：按 judge_key 路由到旧窄函数（+适配器）或 LLM judge。

    需 LLM 的 judge（LLM_JUDGES）走 _run_llm_judge（在调用方的 channel='eval'
    TraceContext scope 内调 LLM）；dsl 走 _run_dsl_judge（try-import 解析器）；
    其余走旧窄函数 + _as_judge_result 适配。

    Args:
        judge_key: judge 类型 key
        expected: 金标准（DatasetItem.expected_output）
        actual: 被测模型回答
        reference: GSB 参照回答（DatasetItem.reference_output）
        config: judge_config（criteria / dsl 文本等）
        model_override: 评判模型覆盖

    Returns:
        JudgeResult；score 恒为 [0, 1] 或 None。
    """
    if judge_key == "dsl":
        return await _run_dsl_judge(
            expected, actual, config=config, model_override=model_override
        )
    if judge_key in LLM_JUDGES:
        return await _run_llm_judge(
            judge_key,
            expected,
            actual,
            reference=reference,
            config=config,
            model_override=model_override,
        )
    judge_fn = JUDGES.get(judge_key)
    if judge_fn is None:
        return JudgeResult(score=None, reason=f"judge 未实现: {judge_key}")
    return _as_judge_result(await judge_fn(expected, actual))


async def _run_llm_judge(
    judge_key: str,
    expected: Any,
    actual: Any,
    *,
    reference: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
    model_override: str | None = None,
) -> JudgeResult:
    """LLM 评分编排：build prompt（纯函数）→ eval 渠道调 LLM → parse_score_result。

    在 run_dataset 的 channel='eval' TraceContext scope 内调用，judge LLM 调用
    自动盖 eval 渠道章（成本 / token 进 Trace）。各模式优雅降级：
    - llm_judge：无 criteria 的 llm_score 退化；expected 缺失返 score=None。
    - llm_score：按 config['criteria'] 出 1-5 档；expected 可空（纯按 criteria 评）。
    - gsb：按 reference 判 G/S/B；reference 缺失返 score=None（无参照不可评）。
    """
    from langchain_core.messages import HumanMessage

    from chameleon.integrations.llms.factory import llm as get_llm
    from chameleon.system.datasets.judges import _flatten_str

    cfg = config or {}
    criteria = cfg.get("criteria")

    if judge_key == "gsb":
        if not _flatten_str(reference).strip():
            return JudgeResult(score=None, reason="GSB 缺参照回答，跳过")
        prompt = build_gsb_prompt(reference, actual, criteria)
        raw = await _ainvoke_llm(get_llm, model_override, HumanMessage, prompt)
        return parse_gsb_result(raw)

    if judge_key == "llm_score":
        prompt = build_llm_score_prompt(expected, actual, criteria)
        raw = await _ainvoke_llm(get_llm, model_override, HumanMessage, prompt)
        return parse_score_result(raw, scale="1-5")

    # judge_key == "llm_judge"（基础 AI 评分）：无 criteria，expected 缺失不可评
    if not _flatten_str(expected).strip():
        return JudgeResult(score=None)
    prompt = build_llm_score_prompt(expected, actual, criteria)
    return parse_score_result(
        await _ainvoke_llm(get_llm, model_override, HumanMessage, prompt),
        scale="1-5",
    )


async def _ainvoke_llm(
    get_llm: Any,
    model_override: str | None,
    human_message_cls: Any,
    prompt: str,
) -> str:
    """单次 LLM 调用取文本（在 eval TraceContext scope 内）。"""
    client = get_llm(model_override)
    ai = await client.ainvoke([human_message_cls(content=prompt)])
    raw = ai.content if hasattr(ai, "content") else str(ai)
    return str(raw)


async def _run_dsl_judge(
    expected: Any,
    actual: Any,
    *,
    config: dict[str, Any] | None = None,
    model_override: str | None = None,
) -> JudgeResult:
    """DSL 评分：parse(config['dsl']) → evaluate（NL 规则用注入的 eval 渠道 LLM）。

    无规则 / 解析全错时返 score=None（reason 带解析错误摘要）；有规则则把 get_llm
    取的客户端注入 evaluate（item 的 channel='eval' TraceContext 已在 run_dataset 外层
    set，evaluator 内不再自建，复用同一 eval 渠道）。
    """
    from chameleon.integrations.llms.factory import llm as get_llm
    from chameleon.system.datasets.dsl import evaluate as dsl_evaluate
    from chameleon.system.datasets.dsl import parse as parse_dsl

    cfg = config or {}
    text = cfg.get("dsl")
    if not isinstance(text, str) or not text.strip():
        return JudgeResult(score=None, scale="1-5", reason="DSL 规则为空")

    spec, errors = parse_dsl(text)
    if spec.is_empty():
        detail = "；".join(errors[:3]) if errors else "无有效规则"
        return JudgeResult(score=None, scale="1-5", reason=f"DSL 无可用规则：{detail}")

    # 仅在有自然语言规则时才取 LLM —— 纯 field 规则 DSL 不需要 LLM，避免未配默认
    # 模型时 LLMFactory 误抛 BusinessError（evaluate 支持 llm=None，仅 NL 规则用 llm）。
    llm = get_llm(model_override) if spec.nl_rules else None
    return await dsl_evaluate(spec, expected, actual, llm=llm)


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
