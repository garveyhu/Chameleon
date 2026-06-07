"""Tool 实现层：全局 registry + 内置工具集。

协议（Tool / ToolContext / ToolResult）在 chameleon.core.tools.base。
import 本包即触发 builtins 注册到全局 registry。
"""

# 触发内置 tools 注册到全局 registry
from chameleon.integrations.tools import builtins  # noqa: F401,E402
from chameleon.integrations.tools.execute import run_tool
from chameleon.integrations.tools.loop import (
    bind_schemas,
    bind_tools,
    extract_tool_calls,
    extract_usage,
    merge_usage,
    run_tool_calls,
    tool_schemas,
)
from chameleon.integrations.tools.registry import (
    all_tool_classes,
    get_tool_class,
    list_tool_keys,
    register_tool,
)

__all__ = [
    "all_tool_classes",
    "bind_schemas",
    "bind_tools",
    "extract_tool_calls",
    "extract_usage",
    "get_tool_class",
    "list_tool_keys",
    "merge_usage",
    "register_tool",
    "run_tool",
    "run_tool_calls",
    "tool_schemas",
]
