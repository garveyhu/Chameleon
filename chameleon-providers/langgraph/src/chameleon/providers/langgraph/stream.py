"""LangGraph astream_events → Chameleon StreamEvent 翻译

LangGraph 的 v2 事件流类型很多，常见的：
  on_chat_model_stream      → delta（token 片段）
  on_chain_start/end        → step（节点级）
  on_tool_start             → tool_call
  on_tool_end               → tool_result
  on_chat_model_end         → metadata (usage)

未识别事件 → 静默忽略（不要让 graph 内部细节灌满流）。
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from chameleon.providers.base.types import StreamEvent, StreamEventType


def translate(event: dict[str, Any]) -> Iterator[StreamEvent]:
    """单个 langgraph event → 0..n 个 StreamEvent"""
    kind = event.get("event")
    name = event.get("name", "")
    data = event.get("data", {})

    if kind == "on_chat_model_stream":
        chunk = data.get("chunk")
        text = _extract_text(chunk)
        if text:
            yield StreamEvent(type=StreamEventType.delta, data={"text": text})
        return

    if kind == "on_chain_start":
        # 仅对非根 chain（节点）emit step running
        # 简化策略：只发 end 事件，避免事件量爆炸
        return

    if kind == "on_chain_end":
        if name and not name.startswith("LangGraph"):
            yield StreamEvent(
                type=StreamEventType.step,
                data={"name": name, "status": "success"},
            )
        else:
            # 根 chain end → 从 final state 提取 citations / tool_calls 等结构化数据
            output = data.get("output") or {}
            if isinstance(output, dict):
                for cit in output.get("citations", []) or []:
                    if isinstance(cit, dict):
                        yield StreamEvent(type=StreamEventType.citation, data=cit)
        return

    if kind == "on_tool_start":
        yield StreamEvent(
            type=StreamEventType.tool_call,
            data={"name": name, "args": _safe_dict(data.get("input"))},
        )
        return

    if kind == "on_tool_end":
        yield StreamEvent(
            type=StreamEventType.tool_result,
            data={"name": name, "result": _safe_json(data.get("output"))},
        )
        return

    if kind == "on_chat_model_end":
        usage = _extract_usage(data.get("output"))
        if usage:
            yield StreamEvent(
                type=StreamEventType.metadata,
                data={"usage": usage},
            )
        return

    # 其它事件忽略


def _extract_text(chunk: Any) -> str:
    """LangGraph chunk 形态可能多样，尽量取 content 文本"""
    if chunk is None:
        return ""
    # AIMessageChunk
    content = getattr(chunk, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        # list of content parts (multimodal); 拼 text 部分
        parts = []
        for p in content:
            if isinstance(p, dict) and p.get("type") == "text":
                parts.append(p.get("text", ""))
            elif isinstance(p, str):
                parts.append(p)
        return "".join(parts)
    if isinstance(chunk, str):
        return chunk
    return ""


def _safe_dict(obj: Any) -> dict[str, Any]:
    if isinstance(obj, dict):
        return obj
    return {"value": _safe_json(obj)}


def _safe_json(obj: Any) -> Any:
    if obj is None or isinstance(obj, (str, int, float, bool, list, dict)):
        return obj
    # 兜底转 str
    return str(obj)


def _extract_usage(output: Any) -> dict[str, int] | None:
    """从 ChatGeneration 输出尝试取 usage_metadata"""
    if output is None:
        return None
    # langchain_core AIMessage / generations
    meta = getattr(output, "usage_metadata", None) or getattr(
        output, "response_metadata", None
    )
    if isinstance(meta, dict):
        # langchain 标准 usage_metadata 形如 {"input_tokens", "output_tokens", "total_tokens"}
        if "input_tokens" in meta or "output_tokens" in meta:
            return {
                "prompt_tokens": meta.get("input_tokens"),
                "completion_tokens": meta.get("output_tokens"),
                "total_tokens": meta.get("total_tokens"),
            }
        # 兜底：直接传
        return meta
    return None
