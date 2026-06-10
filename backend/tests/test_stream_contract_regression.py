"""流式契约回归测试 —— 锁定两个曾击穿全渠道的 P0。

1. HITL paused step 不得击穿 _StreamAggregator：agentkit 暂停时 emit
   `step status="paused"`，聚合器曾因 StepRecord.status 枚举缺 paused 直接
   ValidationError —— embed / /v1/invoke / OpenAI 兼容三条流全部把 pending
   变成 error，HITL 对外面整体失效（playground 不走聚合器所以 e2e 没拦住）。
2. SSE 兜底 error 信封必须带结构化 code：widget 依赖 code 判断 token 失效
   自动重签（40110-40113 族），曾因 code 只在 message 文本里而无法程序化判断。
"""

from __future__ import annotations

import json

from chameleon.core.api.exceptions import BusinessError, ResultCode
from chameleon.core.api.sse import _wrap
from chameleon.core.runtime_types import (
    StreamEvent,
    StreamEventType,
    _StreamAggregator,
)


def _paused_step() -> StreamEvent:
    return StreamEvent(
        type=StreamEventType.step,
        data={
            "name": "human_input_pending",
            "status": "paused",
            "prompt": "金额超阈值，是否批准？",
            "call_index": 0,
            "run_id": "run-1",
        },
    )


def test_aggregator_accepts_paused_step() -> None:
    agg = _StreamAggregator(session_id="s1", request_id="r1")
    agg.feed(_paused_step())  # 不得抛 ValidationError
    assert agg.steps[0].status == "paused"
    assert agg.steps[0].name == "human_input_pending"


def test_aggregator_paused_then_resume_folds_to_final_state() -> None:
    """resume 续跑后同名 step 应折叠为最终态（last-write-wins）"""
    agg = _StreamAggregator(session_id="s1", request_id="r1")
    agg.feed(_paused_step())
    agg.feed(
        StreamEvent(
            type=StreamEventType.step,
            data={"name": "human_input_pending", "status": "success"},
        )
    )
    assert len(agg.steps) == 1
    assert agg.steps[0].status == "success"


def _parse_sse_data(raw: bytes) -> dict | str:
    text = raw.decode("utf-8").removeprefix("data: ").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


async def test_sse_envelope_carries_business_code() -> None:
    async def boom():
        raise BusinessError(ResultCode.JwtInvalid, "embed session 已过期或无效")
        yield  # pragma: no cover —— 使函数成为 async generator

    chunks = [c async for c in _wrap(boom(), log_label="test")]
    envelope = _parse_sse_data(chunks[0])
    assert envelope["error"]["code"] == 40112
    assert envelope["error"]["message"] == "embed session 已过期或无效"
    assert envelope["error"]["type"] == "BusinessError"
    assert _parse_sse_data(chunks[-1]) == "[DONE]"


async def test_sse_envelope_plain_exception_has_no_code() -> None:
    async def boom():
        raise RuntimeError("boom")
        yield  # pragma: no cover

    chunks = [c async for c in _wrap(boom(), log_label="test")]
    envelope = _parse_sse_data(chunks[0])
    assert envelope["error"]["type"] == "RuntimeError"
    assert "code" not in envelope["error"]


# ── SafeIntJSONResponse：公开 API 雪花精度的唯一全局防线 ──


def test_safe_int_response_stringifies_snowflake_ids() -> None:
    """REST 响应边界把超出 JS 安全整数的 int 转 str（全局 default_response_class）。

    这是公开 API 不丢精度的唯一支柱——schema 注解仍是 int，靠它在 wire 上转
    string。若被移除/绕过，外部 JS 客户端按 message_id 寻址的端点全部失效。
    """
    import json as _json

    from chameleon.core.api.response import SafeIntJSONResponse

    body = SafeIntJSONResponse(
        content={
            "id": 58136219874689024,  # 雪花，> 2^53
            "seq": 42,  # 正常小整数不动
            "ok": True,  # bool 不动
            "nested": {"doc_ids": [58136219874689040, 7]},
        }
    ).body
    parsed = _json.loads(body)
    assert parsed["id"] == "58136219874689024"
    assert parsed["seq"] == 42
    assert parsed["ok"] is True
    assert parsed["nested"]["doc_ids"] == ["58136219874689040", 7]
