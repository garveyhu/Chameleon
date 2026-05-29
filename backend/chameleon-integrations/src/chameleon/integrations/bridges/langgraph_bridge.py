"""LangGraph → StreamEvent 翻译桥

任何 agent 想用 LangGraph CompiledGraph 编排，只要：

    from chameleon.integrations.bridges import astream_from_langgraph_graph

    async def astream(cls, ctx):
        graph = cls._get_or_build_graph()
        async for ev in astream_from_langgraph_graph(ctx, graph):
            yield ev

不需要自己写翻译逻辑。
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from typing import Any

from chameleon.providers.base.types import (
    InvokeContext,
    Message,
    StreamEvent,
    StreamEventType,
)

# ── 顶层 API：把 LangGraph CompiledGraph 跑出 Chameleon StreamEvent ─


async def astream_from_langgraph_graph(
    ctx: InvokeContext,
    graph: Any,
    *,
    state_extras: dict[str, Any] | None = None,
) -> AsyncIterator[StreamEvent]:
    """喂 ctx 给 graph，自动翻译事件流

    Args:
        ctx: Chameleon InvokeContext
        graph: LangGraph CompiledGraph（来自 `sg.compile()`）
        state_extras: 额外灌入 state 的字段（如自定义 citations / kb_key 等）
    """
    from chameleon.core.api.exceptions import ProviderInternalError

    messages = ctx_to_langgraph_messages(ctx)
    state: dict[str, Any] = {"messages": messages, "context": ctx.context_vars}
    if state_extras:
        state.update(state_extras)

    try:
        async for raw in graph.astream_events(state, version="v2"):
            for translated in _translate(raw):
                yield translated
    except Exception as e:
        raise ProviderInternalError(message=f"langgraph runtime error: {e}") from e


# ── ctx → langgraph 消息列表 ────────────────────────────


def ctx_to_langgraph_messages(ctx: InvokeContext) -> list[dict]:
    """ctx.history + ctx.input → LangGraph messages（dict 形式，最通用）"""
    msgs: list[dict] = [_msg_to_dict(m) for m in ctx.history]
    if isinstance(ctx.input, str):
        msgs.append({"role": "user", "content": ctx.input})
    else:
        msgs.extend(_msg_to_dict(m) for m in ctx.input)
    return msgs


def _msg_to_dict(m: Message) -> dict:
    d: dict = {"role": m.role, "content": m.content}
    if m.name:
        d["name"] = m.name
    if m.tool_call_id:
        d["tool_call_id"] = m.tool_call_id
    return d


# ── LangGraph astream_events 单事件翻译 ──────────────────


def _translate(event: dict[str, Any]) -> Iterator[StreamEvent]:
    """单个 langgraph event → 0..n 个 StreamEvent

    LangGraph v2 事件类型：
      on_chat_model_stream  → delta（token 片段）
      on_chain_end          → step（节点级）+ 从 root state 抽 citations
      on_tool_start         → tool_call
      on_tool_end           → tool_result
      on_chat_model_end     → metadata (usage)
      其它                   → 静默忽略
    """
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
        # 简化：仅在 end 时 emit step，避免事件量爆炸
        return

    if kind == "on_chain_end":
        if name and not name.startswith("LangGraph"):
            yield StreamEvent(
                type=StreamEventType.step,
                data={"name": name, "status": "success"},
            )
        else:
            # 根 chain end → 从 final state 抽 citations
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
            yield StreamEvent(type=StreamEventType.metadata, data={"usage": usage})
        return


# ── helpers ─────────────────────────────────────────────


def _extract_text(chunk: Any) -> str:
    if chunk is None:
        return ""
    content = getattr(chunk, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
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
    return str(obj)


def _extract_usage(output: Any) -> dict[str, int] | None:
    if output is None:
        return None
    meta = getattr(output, "usage_metadata", None) or getattr(
        output, "response_metadata", None
    )
    if isinstance(meta, dict):
        if "input_tokens" in meta or "output_tokens" in meta:
            return {
                "prompt_tokens": meta.get("input_tokens"),
                "completion_tokens": meta.get("output_tokens"),
                "total_tokens": meta.get("total_tokens"),
            }
        return meta
    return None
