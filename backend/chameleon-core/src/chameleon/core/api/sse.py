"""SSE 流式响应封装

把 `AsyncIterator[dict]` 业务流统一包成 `text/event-stream` 响应：

- 每条 dict 序列化为一行 `data: {json}\n\n`
- 末尾自动追加 `data: [DONE]\n\n` 终止标记，方便前端识别结束
- 业务流抛异常时兜底输出 `{"error": {...}}` chunk + `[DONE]`，不让 SSE 半开
- 统一加 `Cache-Control: no-cache` / `X-Accel-Buffering: no` 头，避免代理缓冲

业务侧只关心"产 dict 流"——这是单一职责的核心。
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from fastapi.responses import StreamingResponse
from loguru import logger

DONE_MARKER = "[DONE]"

# 业务流：产 dict
EventStream = AsyncIterator[dict[str, Any]]
# 工厂：调用一次得到一条业务流（用于把 session 等延迟绑定到 stream 启动时刻）
EventStreamFactory = Callable[[], EventStream] | Callable[[], Awaitable[EventStream]]


def _encode(chunk: dict[str, Any]) -> bytes:
    return f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n".encode("utf-8")


def _encode_done() -> bytes:
    return f"data: {DONE_MARKER}\n\n".encode("utf-8")


async def _wrap(stream: EventStream, *, log_label: str) -> AsyncIterator[bytes]:
    try:
        async for chunk in stream:
            yield _encode(chunk)
    except Exception as e:  # noqa: BLE001
        logger.exception("SSE stream failed | label={}", log_label)
        yield _encode(
            {
                "error": {
                    "type": type(e).__name__,
                    "message": str(e)[:300],
                }
            }
        )
    finally:
        yield _encode_done()


def sse_response(
    stream: EventStream,
    *,
    log_label: str = "sse",
) -> StreamingResponse:
    """把 `AsyncIterator[dict]` 包成 SSE `StreamingResponse`。"""
    return StreamingResponse(
        _wrap(stream, log_label=log_label),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
