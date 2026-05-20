"""SSE 序列化 + StreamingResponse 包装

格式：
  event: <type>
  data: <json>
  \n

保活：每 15s 注释行 `: ping\n\n`（标准 SSE 注释，客户端忽略）
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

from loguru import logger

from chameleon.providers.base.types import StreamEvent

_KEEPALIVE_INTERVAL_SEC = 15.0
_KEEPALIVE_BYTES = b": ping\n\n"


def serialize_sse(event: StreamEvent) -> bytes:
    """单事件 → SSE 字节"""
    body = json.dumps(event.data, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event.type.value}\ndata: {body}\n\n".encode("utf-8")


async def sse_iter(
    source: AsyncIterator[StreamEvent],
    *,
    keepalive_interval: float = _KEEPALIVE_INTERVAL_SEC,
) -> AsyncIterator[bytes]:
    """把 StreamEvent 流转字节流 + 心跳保活

    实现：把 source.__anext__ 作为持久 task，每次以 keepalive_interval 等它；
    超时时仅 yield ping，task 继续运行（不取消）。
    """
    aiter = source.__aiter__()

    async def _next() -> StreamEvent:
        return await aiter.__anext__()

    next_task: asyncio.Task[StreamEvent] | None = asyncio.create_task(_next())
    try:
        while True:
            try:
                # asyncio.wait + timeout：超时不杀 task
                done, _pending = await asyncio.wait(
                    {next_task}, timeout=keepalive_interval
                )
                if not done:
                    yield _KEEPALIVE_BYTES
                    continue
                try:
                    event = next_task.result()
                except StopAsyncIteration:
                    next_task = None
                    return
                yield serialize_sse(event)
                next_task = asyncio.create_task(_next())
            except asyncio.CancelledError:
                # 客户端断开 / 上游取消（A3：调用方负责审计）
                logger.warning("sse stream cancelled by client or upstream")
                raise
    finally:
        if next_task is not None and not next_task.done():
            next_task.cancel()
