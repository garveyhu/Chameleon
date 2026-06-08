"""把 Chameleon 平台工具暴露成 MCP server（Phase B）。

让 Chameleon 的工具能被外部 MCP client（Claude Desktop / Cursor / 别的 agent 框架）
消费——MCP 双向互操作的「server 侧」。用低层 mcp Server（list_tools / call_tool 显式返
JSON Schema dict），动态映射 integrations/tools registry，执行复用 run_tool（含 admin
启停闸门 + TOOL 观测）。
"""

from __future__ import annotations

import json
from typing import Any


def list_platform_tools() -> list[dict[str, Any]]:
    """列平台注册工具为 MCP tool 描述（name/description/inputSchema）。"""
    from chameleon.integrations.tools import all_tool_classes

    out: list[dict[str, Any]] = []
    for key, cls in sorted(all_tool_classes().items()):
        try:
            schema = cls().parameters_schema()
        except Exception:  # noqa: BLE001
            schema = {"type": "object", "properties": {}}
        out.append({"name": key, "description": cls.description or "", "inputSchema": schema})
    return out


async def exec_platform_tool(name: str, arguments: dict[str, Any]) -> str:
    """执行平台工具（走 run_tool：admin 闸门 + 观测），返 JSON 文本（供 MCP TextContent）。"""
    from chameleon.integrations.tools import run_tool

    result = await run_tool(name, arguments or {}, caller="mcp-server")
    return json.dumps(result, ensure_ascii=False, default=str)


def build_mcp_server() -> Any:
    """构造暴露平台工具的低层 MCP Server（list_tools + call_tool 接 registry）。"""
    from mcp import types
    from mcp.server.lowlevel import Server

    server: Any = Server("chameleon")

    @server.list_tools()
    async def _list_tools() -> list[Any]:
        return [
            types.Tool(
                name=t["name"], description=t["description"], inputSchema=t["inputSchema"]
            )
            for t in list_platform_tools()
        ]

    @server.call_tool()
    async def _call_tool(name: str, arguments: dict[str, Any]) -> list[Any]:
        text = await exec_platform_tool(name, arguments)
        return [types.TextContent(type="text", text=text)]

    return server


def build_streamable_app(auth_token: str | None = None) -> tuple[Any, Any]:
    """构造 streamable-http ASGI handler + session manager。

    返回 (asgi_handler, session_manager)：handler 挂到 FastAPI 的 /mcp；session_manager
    的 `.run()` 须在 app lifespan 内进入（管理内部任务组）。stateless + json_response
    简化会话生命周期（每请求独立，无需持久 SSE 会话）。

    auth_token：非空则每请求校验 `X-Dev-Token` header（裸 ASGI mount 绕过 FastAPI
    Depends，必须自校验——否则未鉴权即可经 http 工具构成 SSRF）。
    """
    from mcp.server.streamable_http_manager import StreamableHTTPSessionManager

    server = build_mcp_server()
    manager = StreamableHTTPSessionManager(app=server, stateless=True, json_response=True)

    async def asgi_handler(scope: Any, receive: Any, send: Any) -> None:
        if auth_token:
            headers = dict(scope.get("headers") or [])
            presented = headers.get(b"x-dev-token", b"").decode() or ""
            if presented != auth_token:
                await send(
                    {
                        "type": "http.response.start",
                        "status": 401,
                        "headers": [(b"content-type", b"text/plain; charset=utf-8")],
                    }
                )
                await send({"type": "http.response.body", "body": b"Unauthorized"})
                return
        await manager.handle_request(scope, receive, send)

    return asgi_handler, manager
