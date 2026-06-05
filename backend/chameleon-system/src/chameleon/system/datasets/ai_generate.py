"""模块 H2：AI 扩样 —— 种子样本 few-shot → LLM 流式生成评测候选 + 单条优化。

LLM 调用走 channel='eval'（成本 / token 进 Trace）。生成与入库**解耦**：
本模块只产候选（流式 / 单条），不写库；选中候选由前端走 bulk_import 入库。
"""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.observe import (
    TraceContext,
    reset_trace_context,
    set_trace_context,
)
from chameleon.data.constants import Channel
from chameleon.data.models import DatasetItem

EVAL_APP_ID = "__eval__"
MAX_GENERATE = 50


def _new_eval_trace() -> tuple[Any, str]:
    """设 eval 渠道 TraceContext，返回 (token, request_id)；调用方 finally 复原。"""
    request_id = uuid.uuid4().hex
    token = set_trace_context(
        TraceContext(
            request_id=request_id,
            channel=Channel.EVAL.value,
            app_id=EVAL_APP_ID,
            session_id=f"eval-aigen-{request_id[:8]}",
        )
    )
    return token, request_id


def _chunk_text(chunk: Any) -> str:
    """从 LangChain 流 chunk 取增量文本（content 可能是 str 或分段 list）。"""
    content = getattr(chunk, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for seg in content:
            if isinstance(seg, str):
                parts.append(seg)
            elif isinstance(seg, dict):
                t = seg.get("text")
                if isinstance(t, str):
                    parts.append(t)
        return "".join(parts)
    return ""


def _build_generate_prompt(
    task_description: str, seeds: list[DatasetItem], count: int
) -> str:
    examples = (
        "\n".join(
            f"- 输入：{json.dumps(s.input_payload, ensure_ascii=False)}"
            f" 期望：{json.dumps(s.expected_output, ensure_ascii=False)}"
            for s in seeds[:5]
        )
        or "（暂无种子样本，按任务描述自由生成）"
    )
    return (
        f"你是评测数据生成助手。任务：{task_description}\n"
        f"已有样本风格参考：\n{examples}\n\n"
        f"请仿照风格生成 {count} 条**新的、互不重复**评测样本。"
        "只输出 JSON 数组，每项形如 "
        '{"user_input":"<问题>","answer":"<理想回答>"}，不要任何多余文字。'
    )


async def ai_generate_stream(
    session: AsyncSession,
    dataset_id: int,
    *,
    task_description: str,
    count: int,
) -> AsyncIterator[dict]:
    """流式 AI 扩样：仅在启动时读种子，发流期间不写库。

    chunk 形态（与 SSOT 契约一致）：
    - {"type":"delta","data":{"text":<增量原文>}}：LLM 逐块吐字。
    - {"type":"candidate","data":{"user_input":..,"answer":..}}：流末逐条解析推出。
    - {"type":"done","data":{"count":<n>}}：收尾。

    JSON 数组流式期间无法逐条 parse（未闭合），故 candidate 在流末统一解析后推出，
    delta 期间只显示原文（可读性 + 候选准确性优先，不做不可靠的增量 JSON 解析）。
    """
    from langchain_core.messages import HumanMessage

    from chameleon.integrations.llms.factory import llm as get_llm

    count = max(1, min(count, MAX_GENERATE))
    seeds = (
        (
            await session.execute(
                select(DatasetItem)
                .where(DatasetItem.dataset_id == dataset_id)
                .order_by(DatasetItem.created_at.desc())
                .limit(5)
            )
        )
        .scalars()
        .all()
    )
    prompt = _build_generate_prompt(task_description, list(seeds), count)

    token, _request_id = _new_eval_trace()
    full = ""
    try:
        client = get_llm(None)
        async for chunk in client.astream([HumanMessage(content=prompt)]):
            text = _chunk_text(chunk)
            if text:
                full += text
                yield {"type": "delta", "data": {"text": text}}
    finally:
        reset_trace_context(token)

    candidates = _parse_candidates(full)
    for cand in candidates:
        yield {"type": "candidate", "data": cand}
    yield {"type": "done", "data": {"count": len(candidates)}}


async def refine_candidate(
    *,
    task_description: str,
    candidate: dict[str, Any],
    instruction: str | None,
    mode: str,
) -> dict[str, Any]:
    """单条 AI 优化 / 重新生成（非流式）。

    - optimize：在原候选基础上按 instruction（可空，默认提升质量）改写。
    - regenerate：按 task_description 另起一条同主题但不同的候选（参考原候选去重）。

    返回 {"user_input": str, "answer": str | None}；解析失败容错回原候选。
    """
    from langchain_core.messages import HumanMessage

    from chameleon.integrations.llms.factory import llm as get_llm

    prompt = _build_refine_prompt(task_description, candidate, instruction, mode)

    token, _request_id = _new_eval_trace()
    try:
        client = get_llm(None)
        ai = await client.ainvoke([HumanMessage(content=prompt)])
        raw = ai.content if hasattr(ai, "content") else str(ai)
    finally:
        reset_trace_context(token)

    refined = _parse_one_candidate(str(raw))
    if refined is None:
        return {
            "user_input": str(candidate.get("user_input") or ""),
            "answer": candidate.get("answer"),
        }
    return refined


def _build_refine_prompt(
    task_description: str,
    candidate: dict[str, Any],
    instruction: str | None,
    mode: str,
) -> str:
    ui = str(candidate.get("user_input") or "")
    ans = candidate.get("answer")
    ans_text = ans if isinstance(ans, str) else "（无）"
    original = (
        f"=== 原候选 ===\n问题：{ui}\n理想回答：{ans_text}\n\n"
    )
    json_rule = (
        "只输出单个 JSON 对象，形如 "
        '{"user_input":"<问题>","answer":"<理想回答>"}，不要任何多余文字、'
        "解释或 Markdown 代码块包裹。"
    )
    if mode == "regenerate":
        return (
            f"你是评测数据生成助手。任务：{task_description}\n"
            f"{original}"
            "请另起一条**同主题但与原候选明显不同**的新评测样本（换角度 / 换场景，"
            "避免与原候选重复）。\n" + json_rule
        )
    directive = (instruction or "").strip() or "提升质量，使问题更清晰、回答更严谨准确"
    return (
        f"你是评测数据优化助手。任务背景：{task_description}\n"
        f"{original}"
        f"请基于改写诉求优化这条候选：{directive}\n"
        "保持与原候选同主题，只做质量提升。\n" + json_rule
    )


def _coerce_candidate(x: Any) -> dict[str, Any] | None:
    """单个 dict → {user_input, answer}（容错字段别名）；非法返回 None。"""
    if not isinstance(x, dict):
        return None
    ui = x.get("user_input") or x.get("input") or x.get("question")
    ans = x.get("answer") or x.get("expected") or x.get("output")
    if not isinstance(ui, str) or not ui.strip():
        return None
    return {
        "user_input": ui,
        "answer": ans if isinstance(ans, str) else None,
    }


def _parse_candidates(raw: str) -> list[dict[str, Any]]:
    """从 LLM 输出截取 JSON 数组 → 候选 dict 列表（容错）。"""
    m = re.search(r"\[.*\]", raw, re.DOTALL)
    if not m:
        return []
    try:
        arr: Any = json.loads(m.group(0))
    except (ValueError, TypeError):
        return []
    if not isinstance(arr, list):
        return []
    out: list[dict[str, Any]] = []
    for x in arr:
        cand = _coerce_candidate(x)
        if cand is not None:
            out.append(cand)
    return out


def _parse_one_candidate(raw: str) -> dict[str, Any] | None:
    """从 LLM 输出截取单个 JSON 对象 → 候选 dict（容错，失败返 None）。"""
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        return None
    try:
        obj: Any = json.loads(m.group(0))
    except (ValueError, TypeError):
        return None
    return _coerce_candidate(obj)
