"""DIFY 事件 → Chameleon StreamEvent 翻译

DIFY chat-messages 事件类型（v1 关注的）：
  message            —— delta 文本片段（answer 字段是增量？历史上有变化，按片段处理）
  agent_thought      —— step (thinking)
  agent_message      —— delta（agent 模式下的文本片段）
  message_replace    —— delta（敏感词替换，整体覆盖）
  message_end        —— done + 含 usage / conversation_id
  message_file       —— metadata（附件）忽略 v1
  error              —— error
  ping               —— 忽略（保活）

DIFY workflows/run 事件类型：
  workflow_started   —— 忽略（或 step）
  node_started       —— 忽略（噪音）
  node_finished      —— step
  workflow_finished  —— done + outputs
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from chameleon.providers.base.types import StreamEvent, StreamEventType


def translate_chat(event: dict[str, Any]) -> Iterator[StreamEvent]:
    kind = event.get("event")

    if kind in ("message", "agent_message"):
        text = event.get("answer", "")
        if text:
            yield StreamEvent(type=StreamEventType.delta, data={"text": text})
        return

    if kind == "agent_thought":
        thought = event.get("thought") or event.get("observation") or ""
        if thought:
            yield StreamEvent(
                type=StreamEventType.step,
                data={
                    "name": "agent_thought",
                    "status": "success",
                    "thinking": thought,
                },
            )
        return

    if kind == "message_end":
        usage = _extract_usage(event.get("metadata", {}))
        conv_id = event.get("conversation_id")
        if usage:
            yield StreamEvent(type=StreamEventType.metadata, data={"usage": usage})
        if conv_id:
            yield StreamEvent(
                type=StreamEventType.metadata,
                data={"provider_conv_id": conv_id},
            )
        yield StreamEvent(
            type=StreamEventType.done,
            data={
                "answer": "",  # answer 由聚合器从 delta 累积；provider 不重复
                "provider_conv_id": conv_id,
                "usage": usage,
            },
        )
        return

    if kind == "message_replace":
        # 整体覆盖前面累积的 delta（敏感词改写）。
        # 简化策略：作为新 delta 追加（前后端展示层处理覆盖逻辑）。
        text = event.get("answer", "")
        if text:
            yield StreamEvent(
                type=StreamEventType.delta,
                data={"text": text, "replace": True},
            )
        return

    if kind == "error":
        yield StreamEvent(
            type=StreamEventType.error,
            data={
                "message": event.get("message", "dify error"),
                "code": event.get("code"),
            },
        )
        return

    # ping / message_file / 未知事件 —— 静默忽略


def translate_workflow(event: dict[str, Any]) -> Iterator[StreamEvent]:
    kind = event.get("event")

    if kind == "node_finished":
        data = event.get("data", {})
        yield StreamEvent(
            type=StreamEventType.step,
            data={
                "name": data.get("title") or data.get("node_type") or "node",
                "status": "success" if data.get("status") == "succeeded" else "failed",
                "duration_ms": int((data.get("elapsed_time") or 0) * 1000),
                "output": _safe_json(data.get("outputs")),
            },
        )
        return

    if kind == "workflow_finished":
        data = event.get("data", {})
        outputs = data.get("outputs") or {}
        # answer = outputs 第一个 text 类字段（约定）
        answer = (
            outputs.get("answer")
            or outputs.get("text")
            or (next(iter(outputs.values())) if outputs else "")
        )
        if not isinstance(answer, str):
            answer = str(answer)
        if answer:
            yield StreamEvent(type=StreamEventType.delta, data={"text": answer})
        yield StreamEvent(
            type=StreamEventType.done,
            data={"answer": answer},
        )
        return

    if kind == "error":
        yield StreamEvent(
            type=StreamEventType.error,
            data={"message": event.get("message", "dify workflow error")},
        )
        return


# ── helpers ─────────────────────────────────────────────


def _extract_usage(metadata: dict[str, Any]) -> dict[str, int] | None:
    usage = metadata.get("usage")
    if not isinstance(usage, dict):
        return None
    return {
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "total_tokens": usage.get("total_tokens"),
    }


def _safe_json(obj: Any) -> Any:
    if obj is None or isinstance(obj, (str, int, float, bool, list, dict)):
        return obj
    return str(obj)
