"""Chameleon 作为 MCP server（Phase B）—— 把平台工具暴露给外部 MCP client。"""

from chameleon.api.mcp_server.server import (
    build_mcp_server,
    exec_platform_tool,
    list_platform_tools,
)

__all__ = ["build_mcp_server", "exec_platform_tool", "list_platform_tools"]
