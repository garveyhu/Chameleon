"""dev transport 本地 trace 单测：_DevSpan 记录嵌套 + 耗时（T5-1 杀 NullSpan）。"""

from __future__ import annotations

import pytest

from chameleon.agentkit._dev_transport import HttpDevTransport


@pytest.mark.asyncio
async def test_dev_span_records_nesting_and_duration():
    t = HttpDevTransport(base_url="http://x", token="t")
    async with t.span("outer", type="span"):
        async with t.span("inner", type="generation"):
            pass
    spans = t.drain_spans()
    # 退出顺序：inner 先（内层先退出），outer 后
    assert [s["name"] for s in spans] == ["inner", "outer"]
    assert [s["depth"] for s in spans] == [1, 0]
    assert all("duration_ms" in s and not s["error"] for s in spans)
    # drain 后清空
    assert t.drain_spans() == []


@pytest.mark.asyncio
async def test_dev_span_marks_error():
    t = HttpDevTransport(base_url="http://x", token="t")
    with pytest.raises(ValueError):
        async with t.span("boom"):
            raise ValueError("x")
    spans = t.drain_spans()
    assert len(spans) == 1 and spans[0]["error"] is True
