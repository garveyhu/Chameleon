"""LangChain Runnable → StreamEvent 翻译桥

让 LCEL 风格（prompt | llm | parser）的 agent 无需写翻译就能接入。

用法：

    from chameleon.integrations.bridges import astream_from_runnable
    from chameleon.core.components import llm
    from langchain_core.prompts import ChatPromptTemplate

    class MyAgent(BaseAgent):
        @classmethod
        async def astream(cls, ctx):
            prompt = ChatPromptTemplate.from_messages([
                ("system", "你是一个有用的助手。"),
                ("placeholder", "{history}"),
                ("user", "{input}"),
            ])
            chain = prompt | llm()
            async for ev in astream_from_runnable(
                ctx, chain, input_key="input", history_key="history"
            ):
                yield ev
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from chameleon.providers.base.types import (
    InvokeContext,
    Message,
    StreamEvent,
    StreamEventType,
)


async def astream_from_runnable(
    ctx: InvokeContext,
    runnable: Any,
    *,
    input_key: str = "input",
    history_key: str | None = "history",
    extras: dict[str, Any] | None = None,
    input_mode: str = "auto",
) -> AsyncIterator[StreamEvent]:
    """喂 ctx 给 LangChain Runnable，按 chunk 翻成 delta；end 时 metadata + done

    Args:
        ctx: Chameleon InvokeContext
        runnable: LangChain Runnable（任何 .astream() 可用的对象）
        input_key: prompt 模板里"当前轮问题"的字段名（默认 "input"）
        history_key: prompt 模板里"历史消息"的字段名；None = 不传 history
        extras: 额外灌入 runnable input 的字段
        input_mode: "auto" / "dict" / "messages"
            - dict（含 prompt 模板的完整 chain）→ 传 {input_key, history_key, **extras}
            - messages（裸 LLM 或 ChatModel）→ 传 list[BaseMessage]
            - auto（默认）：探测 runnable 是否含 BaseChatModel 顶层（裸 LLM），自动选 messages
    """
    from chameleon.core.api.exceptions import ProviderInternalError

    mode = _resolve_input_mode(runnable, input_mode)
    if mode == "dict":
        payload: Any = _build_dict_input(
            ctx, input_key=input_key, history_key=history_key, extras=extras
        )
    else:  # messages
        payload = _build_messages_input(ctx)

    accumulated_usage: dict[str, int] | None = None

    try:
        async for chunk in runnable.astream(payload):
            text = _extract_chunk_text(chunk)
            if text:
                yield StreamEvent(type=StreamEventType.delta, data={"text": text})
            # 末 chunk 可能含 usage_metadata
            usage = _extract_usage(chunk)
            if usage:
                accumulated_usage = usage
    except Exception as e:
        raise ProviderInternalError(message=f"runnable astream failed: {e}") from e

    if accumulated_usage:
        yield StreamEvent(
            type=StreamEventType.metadata, data={"usage": accumulated_usage}
        )


def _resolve_input_mode(runnable: Any, requested: str) -> str:
    """auto 模式：识别裸 BaseChatModel 用 messages，其它默认 dict"""
    if requested in ("dict", "messages"):
        return requested
    try:
        from langchain_core.language_models.chat_models import BaseChatModel

        if isinstance(runnable, BaseChatModel):
            return "messages"
    except ImportError:
        pass
    return "dict"


def _build_messages_input(ctx: InvokeContext) -> list:
    """裸 ChatModel 接收 messages 列表"""
    try:
        from langchain_core.messages import (
            AIMessage,
            HumanMessage,
            SystemMessage,
            ToolMessage,
        )
    except ImportError:
        # 没装 langchain_core 时降级 dict 列表
        msgs = [{"role": m.role, "content": m.content} for m in ctx.history]
        if isinstance(ctx.input, str):
            msgs.append({"role": "user", "content": ctx.input})
        else:
            msgs.extend({"role": m.role, "content": m.content} for m in ctx.input)
        return msgs

    out: list = []
    for m in ctx.history:
        out.append(
            _to_lc_message(m, HumanMessage, AIMessage, SystemMessage, ToolMessage)
        )
    if isinstance(ctx.input, str):
        out.append(HumanMessage(content=ctx.input))
    else:
        for m in ctx.input:
            out.append(
                _to_lc_message(m, HumanMessage, AIMessage, SystemMessage, ToolMessage)
            )
    return out


def _to_lc_message(m, HumanMessage, AIMessage, SystemMessage, ToolMessage):
    if m.role == "user":
        return HumanMessage(content=m.content)
    if m.role == "assistant":
        return AIMessage(content=m.content)
    if m.role == "system":
        return SystemMessage(content=m.content)
    if m.role == "tool":
        return ToolMessage(content=m.content, tool_call_id=m.tool_call_id or "")
    return HumanMessage(content=m.content)


# ── helpers ─────────────────────────────────────────────


def _build_dict_input(
    ctx: InvokeContext,
    *,
    input_key: str,
    history_key: str | None,
    extras: dict[str, Any] | None,
) -> dict[str, Any]:
    """含 prompt 模板的 chain 接收 dict payload"""
    payload: dict[str, Any] = {}

    if isinstance(ctx.input, str):
        payload[input_key] = ctx.input
        if history_key:
            payload[history_key] = _history_to_lc(ctx.history)
    else:
        # list[Message]：最后一条 user 是当前轮；其余进 history
        msgs = list(ctx.input)
        last_user_text = ""
        for m in reversed(msgs):
            if m.role == "user":
                last_user_text = m.content
                break
        payload[input_key] = last_user_text
        if history_key:
            # 历史 = 列表中除最后一条 user 外的所有消息（按 client 顺序）
            history = [
                m for m in msgs if m.content != last_user_text or m.role != "user"
            ]
            payload[history_key] = _history_to_lc(history)

    if extras:
        payload.update(extras)
    return payload


def _history_to_lc(history: list[Message]) -> list:
    """ctx.history → LangChain placeholder 需要的 list[BaseMessage] 或 dict"""
    try:
        from langchain_core.messages import (
            AIMessage,
            HumanMessage,
            SystemMessage,
            ToolMessage,
        )
    except ImportError:
        # 没装 langchain_core 时退化为 dict 形式
        return [{"role": m.role, "content": m.content} for m in history]

    out = []
    for m in history:
        if m.role == "user":
            out.append(HumanMessage(content=m.content))
        elif m.role == "assistant":
            out.append(AIMessage(content=m.content))
        elif m.role == "system":
            out.append(SystemMessage(content=m.content))
        elif m.role == "tool":
            out.append(
                ToolMessage(content=m.content, tool_call_id=m.tool_call_id or "")
            )
        else:
            out.append(HumanMessage(content=m.content))
    return out


def _extract_chunk_text(chunk: Any) -> str:
    """Runnable.astream 产的 chunk 可能是 AIMessageChunk / str / dict"""
    if chunk is None:
        return ""
    # AIMessageChunk
    content = getattr(chunk, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [
            p.get("text", "")
            for p in content
            if isinstance(p, dict) and p.get("type") == "text"
        ]
        return "".join(parts)
    if isinstance(chunk, str):
        return chunk
    if isinstance(chunk, dict):
        return str(chunk.get("text") or chunk.get("content") or "")
    return ""


def _extract_usage(chunk: Any) -> dict[str, int] | None:
    meta = getattr(chunk, "usage_metadata", None)
    if isinstance(meta, dict) and ("input_tokens" in meta or "output_tokens" in meta):
        return {
            "prompt_tokens": meta.get("input_tokens"),
            "completion_tokens": meta.get("output_tokens"),
            "total_tokens": meta.get("total_tokens"),
        }
    return None
