"""模块 H2：AI 扩样 —— 种子样本 few-shot → LLM 批量生成新评测样本。

LLM 调用走 channel='eval'（成本 / token 进 Trace），生成的样本复用 bulk_import 入库。
"""

from __future__ import annotations

import json
import re
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.api.exceptions import BusinessError, ResultCode
from chameleon.core.observe import (
    TraceContext,
    reset_trace_context,
    set_trace_context,
)
from chameleon.data.constants import Channel
from chameleon.data.models import DatasetItem
from chameleon.system.datasets.schemas import BulkImportItem, BulkImportRequest

EVAL_APP_ID = "__eval__"
MAX_GENERATE = 50


async def ai_generate_items(
    session: AsyncSession,
    dataset_id: int,
    *,
    task_description: str,
    count: int,
) -> int:
    """种子样本 few-shot → LLM 生成 count 个新样本入库；返回新增条数。"""
    from chameleon.system.datasets import service as ds_service

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

    items = await _llm_generate(task_description, list(seeds), count)
    if not items:
        raise BusinessError(
            ResultCode.Fail, message="AI 未生成有效样本，请调整任务描述后重试"
        )

    result = await ds_service.bulk_import_items(
        session,
        dataset_id,
        BulkImportRequest(items=items, pii_strategy="keep"),
    )
    return result.added


async def _llm_generate(
    task_description: str,
    seeds: list[DatasetItem],
    count: int,
) -> list[BulkImportItem]:
    from langchain_core.messages import HumanMessage

    from chameleon.integrations.llms.factory import llm as get_llm

    examples = (
        "\n".join(
            f"- 输入：{json.dumps(s.input_payload, ensure_ascii=False)}"
            f" 期望：{json.dumps(s.expected_output, ensure_ascii=False)}"
            for s in seeds[:5]
        )
        or "（暂无种子样本，按任务描述自由生成）"
    )

    prompt = (
        f"你是评测数据生成助手。任务：{task_description}\n"
        f"已有样本风格参考：\n{examples}\n\n"
        f"请仿照风格生成 {count} 条**新的、互不重复**评测样本。"
        "只输出 JSON 数组，每项形如 "
        '{"user_input":"<问题>","answer":"<理想回答>"}，不要任何多余文字。'
    )

    request_id = uuid.uuid4().hex
    token = set_trace_context(
        TraceContext(
            request_id=request_id,
            channel=Channel.EVAL.value,
            app_id=EVAL_APP_ID,
            session_id=f"eval-aigen-{request_id[:8]}",
        )
    )
    try:
        client = get_llm(None)
        ai = await client.ainvoke([HumanMessage(content=prompt)])
        raw = ai.content if hasattr(ai, "content") else str(ai)
    finally:
        reset_trace_context(token)

    return _parse_generated(str(raw))


def _parse_generated(raw: str) -> list[BulkImportItem]:
    """从 LLM 输出截取 JSON 数组 → BulkImportItem 列表（容错）。"""
    m = re.search(r"\[.*\]", raw, re.DOTALL)
    if not m:
        return []
    try:
        arr: Any = json.loads(m.group(0))
    except (ValueError, TypeError):
        return []
    if not isinstance(arr, list):
        return []

    out: list[BulkImportItem] = []
    for x in arr:
        if not isinstance(x, dict):
            continue
        ui = x.get("user_input") or x.get("input") or x.get("question")
        ans = x.get("answer") or x.get("expected") or x.get("output")
        if not isinstance(ui, str) or not ui.strip():
            continue
        out.append(
            BulkImportItem(
                input_payload={"user_input": ui},
                expected_output={"answer": ans} if isinstance(ans, str) else None,
                meta={"source": "ai_generate"},
            )
        )
    return out
