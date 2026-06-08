"""MCP tool → 中性工具描述符适配。

把外部 MCP server 的 tools 适配成中性 `McpToolDescriptor`（name/description/
parameters_schema/handler）。上层 runner 再把它包成 agentkit `ToolSpec` 并入
`run_with_tools` 的本地工具——零改动复用整条 ReAct 循环（自动 emit/trace/成本闸）。

本层不依赖 agentkit（返中性 dataclass，避免 integrations→agentkit 反向耦合）。
"""

from __future__ import annotations

from contextlib import AsyncExitStack
from dataclasses import dataclass
from typing import Any

from loguru import logger

from chameleon.integrations.mcp.client import flatten_tool_result, open_session


@dataclass
class McpToolDescriptor:
    """中性 MCP 工具描述符（runner 据此造 agentkit ToolSpec）。"""

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
            logger.warning("MCP server 连接/列举失败 cfg={}: {}", cfg.get("name") or cfg, e)
    return descriptors, stack
