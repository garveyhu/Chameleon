"""MCP（Model Context Protocol）client —— 让 @agent 消费外部 MCP server 的 tools。

属 authoring 关注点（agent 用别人的工具），故置于 agentkit 而非 integrations：站内
InProcessTransport（providers-local）与本地 dev（HttpDevTransport）两端都从这里连 MCP
server，轻量 dev 环境无需安装重的 integrations。

把外部 MCP tools 适配成中性 `McpToolDescriptor`（name/description/parameters_schema/
handler），上层 runner/transport 再包成 ToolSpec 并入 ReAct 循环——零改动复用工具循环。

依赖 mcp SDK（agentkit 核心依赖）。stdio / streamable-http / sse 三 transport 统一。
"""

from __future__ import annotations

import logging
from contextlib import AsyncExitStack
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


# ── 连接层 ──────────────────────────────────────────────


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


# ── 适配层 ──────────────────────────────────────────────


@dataclass
class McpToolDescriptor:
    """中性 MCP 工具描述符（runner/transport 据此造 ToolSpec）。"""

    name: str
    description: str
    parameters_schema: dict[str, Any]
    handler: Any  # async (**args) -> dict


def _make_descriptor(session: Any, tool: Any, exposed_name: str) -> McpToolDescriptor:
    real_name = tool.name

    async def handler(**args: Any) -> dict[str, Any]:
        result = await session.call_tool(real_name, args)
        return flatten_tool_result(result)

    return McpToolDescriptor(
        name=exposed_name,
        description=tool.description or "",
        parameters_schema=tool.inputSchema or {"type": "object", "properties": {}},
        handler=handler,
    )


async def load_mcp_tools(
    server_configs: list[dict[str, Any]],
) -> tuple[list[McpToolDescriptor], AsyncExitStack]:
    """连接所有 MCP server，列举并适配其 tools。

    Returns:
        (descriptors, stack)。stack 必须由调用方在 agent 运行结束后 `aclose()`（防泄漏）。
        单个 server 连接 / 列举失败仅 warning + 跳过，不拖垮 agent。
        多 server 时工具名加 `<server>.` 前缀消歧。
    """
    stack = AsyncExitStack()
    descriptors: list[McpToolDescriptor] = []
    multi = len(server_configs) > 1
    for cfg in server_configs:
        prefix = cfg.get("name") or ""
        try:
            session = await open_session(stack, cfg)
            resp = await session.list_tools()
            for t in resp.tools:
                exposed = f"{prefix}.{t.name}" if (multi and prefix) else t.name
                descriptors.append(_make_descriptor(session, t, exposed))
        except Exception as e:  # noqa: BLE001
            logger.warning("MCP server 连接/列举失败 cfg=%s: %s", cfg.get("name") or cfg, e)
    return descriptors, stack
