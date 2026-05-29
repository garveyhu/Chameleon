"""Chameleon Tool 协议 + 内置工具集"""

# 触发内置 tools 注册到全局 registry
from chameleon.core.tools import builtins  # noqa: F401,E402
from chameleon.core.tools.base import Tool, ToolContext, ToolResult
from chameleon.core.tools.registry import (
    all_tool_classes,
    get_tool_class,
    list_tool_keys,
    register_tool,
)

__all__ = [
    "Tool",
    "ToolContext",
    "ToolResult",
    "all_tool_classes",
    "get_tool_class",
    "list_tool_keys",
    "register_tool",
]
