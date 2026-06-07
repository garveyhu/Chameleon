"""LLMNode 工具支持 —— graph 适配层。

通用 ReAct / function-calling 原语（bind_tools / extract_* / merge_usage /
run_tool_calls）已下沉到 `chameleon.integrations.tools.loop`，与 graph 解耦，供
graph LLMNode 与 agentkit 共用。本模块只保留 graph 侧的薄封装：把 NodeContext 的
graph_run_id / graph_id / node_id 翻成通用 run_tool_calls 的 caller/related_id/extra。
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import ToolMessage

from chameleon.engine.graph.context import NodeContext
from chameleon.integrations.tools.loop import (
    bind_tools,
    extract_tool_calls,
    extract_usage,
    merge_usage,
)
from chameleon.integrations.tools.loop import (
    run_tool_calls as _run_tool_calls_generic,
)

__all__ = [
    "bind_tools",
    "extract_tool_calls",
    "extract_usage",
    "merge_usage",
    "run_tool_calls",
]


async def run_tool_calls(
    tool_calls: list[dict[str, Any]],
    ctx: NodeContext,
    node_id: str,
) -> tuple[list[ToolMessage], list[dict[str, Any]]]:
    """跑一轮 tool_calls（graph LLMNode 入口）。

    薄封装：从 NodeContext 取 graph_run_id / graph_id，转调
    `integrations.tools.loop.run_tool_calls`（与 ToolNode 同一执行入口，不分叉）。
    """
    return await _run_tool_calls_generic(
        tool_calls,
        caller="llm-node",
        related_id=str(ctx.graph_run_id),
        extra={"graph_id": ctx.graph_id, "node_id": node_id},
    )
