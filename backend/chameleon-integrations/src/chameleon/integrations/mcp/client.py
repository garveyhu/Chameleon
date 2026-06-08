"""MCP（Model Context Protocol）client 连接层。

把官方 mcp SDK 的 stdio / streamable-http / sse transport 统一成「开会话 → list_tools →
call_tool → 关闭」。连接生命周期用 AsyncExitStack 托管：会话在 agent handle 运行期间
保持打开，结束时统一关闭（防 stdio 子进程 / HTTP 连接泄漏）。

mcp SDK 只在本层（integrations）依赖；上层（agentkit / runner）经中性描述符消费，
不 import mcp。
"""

from __future__ import annotations

from contextlib import AsyncExitStack
from typing import Any


async def open_session(stack: AsyncExitStack, cfg: dict[str, Any]) -> Any:
    """按 cfg 打开一个 MCP ClientSession（已 initialize），注册进 stack 待统一关闭。

    cfg: {transport: stdio|http|sse, ...}
      - stdio: command（必填）/ args / env
      - http / sse: url（必填）/ headers
    """
    from mcp import ClientSession

    transport = (cfg.get("transport") or "stdio").lower()
    if transport == "stdio":
        from mcp import StdioServerParameters
        from mcp.client.stdio import stdio_client

        params = StdioServerParameters(
            command=cfg["command"],
            args=list(cfg.get("args") or []),
            env=cfg.get("env"),
        )
        read, write = await stack.enter_async_context(stdio_client(params))
    elif transport in ("http", "streamable-http", "streamable_http"):
        from mcp.client.streamable_http import streamablehttp_client

        read, write, _ = await stack.enter_async_context(
            streamablehttp_client(cfg["url"], headers=cfg.get("headers"))
        )
    elif transport == "sse":
        from mcp.client.sse import sse_client

        read, write = await stack.enter_async_context(
            sse_client(cfg["url"], headers=cfg.get("headers"))
        )
    else:
        raise ValueError(f"unsupported MCP transport: {transport}")

    session = await stack.enter_async_context(ClientSession(read, write))
    await session.initialize()
    return session


def flatten_tool_result(result: Any) -> dict[str, Any]:
    """把 MCP CallToolResult 摊平成 JSON-able dict（供 ToolMessage 回填模型）。"""
    is_error = bool(getattr(result, "isError", False))
    structured = getattr(result, "structuredContent", None)
    if structured:
        return {"ok": not is_error, "data": structured, "error": None if not is_error else "tool error"}
    parts: list[str] = []
    for c in getattr(result, "content", None) or []:
        ctype = getattr(c, "type", None)
        if ctype == "text":
            parts.append(getattr(c, "text", ""))
        elif ctype in ("image", "audio"):
            parts.append(f"[{ctype}]")
        elif ctype == "resource":
            parts.append(f"[resource:{getattr(getattr(c, 'resource', None), 'uri', '')}]")
    text = "\n".join(p for p in parts if p)[:8000]
    return {"ok": not is_error, "data": text, "error": text if is_error else None}
