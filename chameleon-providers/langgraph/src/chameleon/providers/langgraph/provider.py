"""LangGraphProvider —— in-process 调用本地 LangGraph agent

约定：
- agent 子包 __init__.py export build_graph() —— sync function 返 CompiledGraph
- build_graph 仅在首次调用时执行，结果缓存于 GraphBuilder
- ctx.history + ctx.input 翻成 langgraph 消息列表喂入 graph
- graph.astream_events(version="v2") 输出 → stream.translate → StreamEvent
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from loguru import logger

from chameleon.core.exceptions import ProviderInternalError
from chameleon.providers.base.protocol import Provider
from chameleon.providers.base.types import (
    InvokeContext,
    Message,
    StreamEvent,
)
from chameleon.providers.langgraph.builder import GraphBuilder
from chameleon.providers.langgraph.stream import translate


class LangGraphProvider(Provider):
    name = "langgraph"

    def __init__(self) -> None:
        self._builder = GraphBuilder()

    async def stream(self, ctx: InvokeContext) -> AsyncIterator[StreamEvent]:
        graph = await self._builder.get_or_build(ctx.agent_def)

        messages = _build_messages(ctx)
        state_input = {"messages": messages, "context": ctx.context_vars}

        # graph.astream_events 返回 async iterator
        try:
            async for ev in graph.astream_events(state_input, version="v2"):
                for out in translate(ev):
                    yield out
        except Exception as e:
            logger.exception("langgraph stream failed | agent={}", ctx.agent_def.key)
            raise ProviderInternalError(message=f"langgraph runtime error: {e}") from e

    async def healthcheck(self) -> bool:
        # in-process —— 总是 True
        return True


def _build_messages(ctx: InvokeContext) -> list[dict]:
    """把 ctx.history + 当前 input 翻成 langgraph dict-form messages

    LangGraph MessagesState 接受 dict {"role": ..., "content": ...} 或
    LangChain BaseMessage —— dict 形式最通用。
    """
    msgs: list[dict] = [_msg_to_dict(m) for m in ctx.history]

    if isinstance(ctx.input, str):
        msgs.append({"role": "user", "content": ctx.input})
    else:
        # list[Message] —— 当前轮 = 整个 list（client 自管历史时 history 应为空）
        msgs.extend(_msg_to_dict(m) for m in ctx.input)

    return msgs


def _msg_to_dict(m: Message) -> dict:
    d: dict = {"role": m.role, "content": m.content}
    if m.name:
        d["name"] = m.name
    if m.tool_call_id:
        d["tool_call_id"] = m.tool_call_id
    return d
