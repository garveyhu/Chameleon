"""MCP（Model Context Protocol）互操作 —— client 连接 + tool 适配。

mcp SDK 只在本包依赖；上层经中性 McpToolDescriptor 消费。
"""

from chameleon.integrations.mcp.adapter import McpToolDescriptor, load_mcp_tools
from chameleon.integrations.mcp.client import flatten_tool_result, open_session

__all__ = [
    "McpToolDescriptor",
    "flatten_tool_result",
    "load_mcp_tools",
    "open_session",
]
