"""FastGPT SSE → Chameleon StreamEvent

FastGPT 事件类型（detail=true 时）：
  answer        —— OpenAI 标准 chunk（choices[0].delta.content 是 delta 文本）
  flowNodeStatus / flowResponses  —— flow 节点状态/输出
  toolCall      —— 工具调用
  fastAnswer    —— 完整 answer 替代（少见）
  无 event:     —— 当 answer chunk

最后通过 [DONE] 行结束。我们在 client._sse_request 已剥离 [DONE]。
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from chameleon.providers.base.types import StreamEvent, StreamEventType


def translate(event: dict[str, Any]) -> Iterator[StreamEvent]:
    kind = event.get("event")
    data = event.get("data", {})

    if kind == "answer":
        text = _extract_delta_text(data)
        if text:
            yield StreamEvent(type=StreamEventType.delta, data={"text": text})
        # 收尾标记
        if _is_finish(data):
            usage = _extract_usage(data)
            yield StreamEvent(
                type=StreamEventType.done,
                data={"usage": usage} if usage else {},
            )
        return

    if kind == "flowNodeStatus":
        # data 形如 {"status": "running", "name": "..." } —— v1 忽略 running，只保留 completed
        if data.get("status") == "completed":
            yield StreamEvent(
                type=StreamEventType.step,
                data={"name": data.get("name", "node"), "status": "success"},
            )
        return

    if kind == "flowResponses":
        # data: list[dict] 各 node 的 output —— 当 metadata
        if isinstance(data, list):
            yield StreamEvent(
                type=StreamEventType.metadata, data={"flow_responses": data}
            )
        return

    if kind == "toolCall":
        yield StreamEvent(
            type=StreamEventType.tool_call,
            data={
                "name": data.get("name", "tool"),
                "args": data.get("params"),
                "result": data.get("response"),
            },
        )
        return

    if kind == "error":
        yield StreamEvent(
            type=StreamEventType.error,
            data={"message": data.get("message", "fastgpt error")},
        )
        return

    # 其它静默忽略


# ── helpers ─────────────────────────────────────────────


def _extract_delta_text(data: dict[str, Any]) -> str:
    """OpenAI 兼容 chunk：choices[0].delta.content"""
    choices = data.get("choices", [])
    if not choices:
        return ""
    delta = choices[0].get("delta", {})
    if not isinstance(delta, dict):
        return ""
    content = delta.get("content")
    if isinstance(content, str):
        return content
    return ""


def _is_finish(data: dict[str, Any]) -> bool:
    choices = data.get("choices", [])
    if not choices:
        return False
    return choices[0].get("finish_reason") is not None


def _extract_usage(data: dict[str, Any]) -> dict[str, int] | None:
    usage = data.get("usage")
    if not isinstance(usage, dict):
        return None
    return {
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "total_tokens": usage.get("total_tokens"),
    }
