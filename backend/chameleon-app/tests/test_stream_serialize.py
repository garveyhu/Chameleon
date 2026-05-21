"""SSE 序列化 + 保活心跳单测"""

import asyncio
import json
from collections.abc import AsyncIterator

import pytest

from chameleon.api.agent.stream import (
    _KEEPALIVE_BYTES,
    serialize_sse,
    sse_iter,
)
from chameleon.providers.base.types import StreamEvent, StreamEventType


def test_serialize_delta() -> None:
    ev = StreamEvent(type=StreamEventType.delta, data={"text": "hi"})
    out = serialize_sse(ev).decode("utf-8")
    assert out == 'event: delta\ndata: {"text":"hi"}\n\n'


def test_serialize_done_with_unicode() -> None:
    ev = StreamEvent(
        type=StreamEventType.done,
        data={"answer": "今天", "session_id": "sess_x"},
    )
    out = serialize_sse(ev).decode("utf-8")
    assert out.startswith("event: done\ndata: ")
    body = out.split("\ndata: ", 1)[1].rstrip("\n")
    assert json.loads(body) == {"answer": "今天", "session_id": "sess_x"}


async def _make_source(events: list[StreamEvent]) -> AsyncIterator[StreamEvent]:
    for e in events:
        yield e


async def test_sse_iter_basic() -> None:
    events = [
        StreamEvent(type=StreamEventType.delta, data={"text": "a"}),
        StreamEvent(type=StreamEventType.done, data={"answer": "a"}),
    ]
    chunks = []
    async for c in sse_iter(_make_source(events)):
        chunks.append(c)
    assert len(chunks) == 2
    assert chunks[0].decode().startswith("event: delta\n")
    assert chunks[1].decode().startswith("event: done\n")


async def test_sse_iter_keepalive_on_slow_source() -> None:
    """source 在 keepalive 间隔内没出数据 → yield 心跳"""

    async def slow_source() -> AsyncIterator[StreamEvent]:
        await asyncio.sleep(0.25)  # 比 keepalive 长，确保至少 1 个 ping
        yield StreamEvent(type=StreamEventType.done, data={"answer": "ok"})

    chunks = []
    async for c in sse_iter(slow_source(), keepalive_interval=0.05):
        chunks.append(c)

    # 至少有 1 个 ping + 最后 1 个 done event
    pings = [c for c in chunks if c == _KEEPALIVE_BYTES]
    events = [c for c in chunks if c != _KEEPALIVE_BYTES]
    assert len(pings) >= 1, f"expected at least 1 ping, got {len(pings)}"
    assert len(events) == 1
    assert events[0].decode().startswith("event: done\n")


async def test_sse_iter_cancellation_propagates() -> None:
    """客户端断开 / asyncio.CancelledError → sse_iter 应抛出（让上层 finally 触发审计）"""

    async def hanging_source() -> AsyncIterator[StreamEvent]:
        await asyncio.Event().wait()  # 永远等
        yield StreamEvent(type=StreamEventType.done, data={})  # 不会到

    async def consumer() -> None:
        async for _ in sse_iter(hanging_source(), keepalive_interval=10):
            pass

    task = asyncio.create_task(consumer())
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
