"""模块 H3：智能优化 —— 当前 Prompt + 评测低分样本 → LLM 重写 Prompt + 优化报告。

汇总该 run 的低分样本（输入/期望/实际）共性缺陷，让 LLM 产出更好的 System Prompt
和优化报告。LLM 调用走 channel='eval'（成本进 Trace）。
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.api.exceptions import BusinessError, ResultCode
from chameleon.core.observe import (
    TraceContext,
    reset_trace_context,
    set_trace_context,
)
from chameleon.data.constants import Channel
from chameleon.data.models import DatasetItem, DatasetRun, DatasetRunItem

EVAL_APP_ID = "__eval__"
LOW_SCORE_THRESHOLD = 0.6
MAX_WEAK_SAMPLES = 12


async def optimize_run_prompt(session: AsyncSession, run_id: int) -> dict[str, Any]:
    """取 run 的低分样本 + 当前 prompt → LLM 生成优化 prompt + 报告。"""
    run = (
        await session.execute(select(DatasetRun).where(DatasetRun.id == run_id))
    ).scalar_one_or_none()
    if run is None:
        raise BusinessError(ResultCode.Fail, message=f"运行不存在: {run_id}")

    all_rows = (
        await session.execute(
            select(DatasetRunItem, DatasetItem)
            .join(DatasetItem, DatasetItem.id == DatasetRunItem.dataset_item_id)
            .where(DatasetRunItem.dataset_run_id == run_id)
        )
    ).all()
    # score 是 JSON 列，数值比较放 Python 做（避免 SQL json < float 不支持）
    weak = [
        (ri, item)
        for ri, item in all_rows
        if isinstance(ri.score, (int, float)) and ri.score < LOW_SCORE_THRESHOLD
    ]
    weak.sort(key=lambda x: float(x[0].score))
    rows = weak[:MAX_WEAK_SAMPLES]
    if not rows:
        raise BusinessError(ResultCode.Fail, message="该运行没有低分样本，无需优化")

    original = run.prompt_override or ""
    weak_block = "\n\n".join(
        f"【输入】{_short(item.input_payload)}\n"
        f"【期望】{_short(item.expected_output)}\n"
        f"【实际(得分 {ri.score})】{_short(ri.actual_output)}"
        for ri, item in rows
    )

    result = await _llm_optimize(original, weak_block, len(rows))

    # H3 落库（幂等覆盖）：优化产出挂在「被优化的 run」自身上，重复点覆盖上次
    run.optimized_prompt = result.get("optimized_prompt", "")
    run.optimization_report = {
        "report": result.get("report", ""),
        "weak_count": len(rows),
        "threshold": LOW_SCORE_THRESHOLD,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    await session.commit()

    return {
        "run_id": run_id,
        "original_prompt": original,
        "optimized_prompt": result.get("optimized_prompt", ""),
        "report": result.get("report", ""),
        "weak_count": len(rows),
    }


async def apply_optimized_run(session: AsyncSession, run_id: int) -> DatasetRun:
    """用父 run 的 optimized_prompt 重跑整个 dataset，落新子 run（版本链）。

    完全复用现有 runner.run_dataset（零引擎改造）：把 optimized_prompt 当 prompt_override
    传进去，跑完把 new_run.parent_run_id 指回父 run，形成 run→run 版本链。

    Args:
        session: DB 会话
        run_id: 被优化的父 run id（其 optimized_prompt 非空）

    Returns:
        重跑得到的新子 run（parent_run_id 指向 run_id）。

    Raises:
        BusinessError: run 不存在 / 未优化 / agent 路径（prompt_override 不透传）。
    """
    from chameleon.system.datasets import runner as ds_runner

    parent = (
        await session.execute(select(DatasetRun).where(DatasetRun.id == run_id))
    ).scalar_one_or_none()
    if parent is None:
        raise BusinessError(ResultCode.Fail, message=f"运行不存在: {run_id}")
    if not (parent.optimized_prompt or "").strip():
        raise BusinessError(
            ResultCode.Fail, message="该运行尚未优化，先点智能优化"
        )
    if parent.agent_key is not None:
        raise BusinessError(
            ResultCode.Fail,
            message="智能体运行的 Prompt 改写需在工作流编排里改，暂不支持一键应用",
        )

    # 默认版本号 n：父 run 已有子版本数 + 1（仅用于命名，不入列）
    child_count = (
        await session.execute(
            select(func.count())
            .select_from(DatasetRun)
            .where(DatasetRun.parent_run_id == run_id)
        )
    ).scalar_one()
    n = child_count + 1

    new_run = await ds_runner.run_dataset(
        session,
        dataset_id=parent.dataset_id,
        name=f"{parent.name} · 优化v{n}",
        model_override=parent.model_override,
        prompt_override=parent.optimized_prompt,
        judge=parent.judge,
        agent_key=None,
    )
    new_run.parent_run_id = run_id
    await session.commit()
    await session.refresh(new_run)
    return new_run


def _short(v: Any) -> str:
    if v is None:
        return "（空）"
    s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
    return s[:200]


async def _llm_optimize(original: str, weak_block: str, n: int) -> dict[str, str]:
    from langchain_core.messages import HumanMessage

    from chameleon.integrations.llms.factory import llm as get_llm

    prompt = (
        "你是 Prompt 优化专家。下面是一个 System Prompt 及它在评测中得分较低的样本"
        "（输入 / 期望 / 实际）。请分析这些低分样本暴露的**共性缺陷**，重写出一个"
        "更好的 System Prompt，并给出优化报告。\n\n"
        f"【当前 System Prompt】\n{original or '（空，模型直调无系统提示）'}\n\n"
        f"【{n} 条低分样本】\n{weak_block}\n\n"
        '只输出 JSON：{"optimized_prompt":"<重写后的完整 System Prompt>",'
        '"report":"<优化报告：低分共性缺陷 + 改了哪些点 + 为什么这样改>"}'
    )
    request_id = uuid.uuid4().hex
    token = set_trace_context(
        TraceContext(
            request_id=request_id,
            channel=Channel.EVAL.value,
            app_id=EVAL_APP_ID,
            session_id=f"eval-opt-{request_id[:8]}",
        )
    )
    try:
        ai = await get_llm(None).ainvoke([HumanMessage(content=prompt)])
        raw = ai.content if hasattr(ai, "content") else str(ai)
    finally:
        reset_trace_context(token)
    return _parse(str(raw))


def _parse(raw: str) -> dict[str, str]:
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        return {"optimized_prompt": "", "report": raw.strip()[:1000]}
    try:
        d = json.loads(m.group(0))
    except (ValueError, TypeError):
        return {"optimized_prompt": "", "report": raw.strip()[:1000]}
    return {
        "optimized_prompt": str(d.get("optimized_prompt", "")),
        "report": str(d.get("report", "")),
    }
