"""Tool 实现层：全局 registry + 内置工具集。

协议（Tool / ToolContext / ToolResult）在 chameleon.core.tools.base。
import 本包即触发 builtins 注册到全局 registry。
"""

# 触发内置 tools 注册到全局 registry
from chameleon.integrations.tools import builtins  # noqa: F401,E402
from chameleon.integrations.tools.registry import (
    all_tool_classes,
    get_tool_class,
    list_tool_keys,
    register_tool,
)

__all__ = [
    "all_tool_classes",
    "get_tool_class",
    "list_tool_keys",
    "register_tool",
]
