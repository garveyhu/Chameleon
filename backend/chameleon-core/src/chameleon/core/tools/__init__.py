"""Chameleon Tool 协议

仅导出协议 / 数据结构（Tool / ToolContext / ToolResult）。
registry 工厂与 builtins 实现已迁至 chameleon.integrations.tools。
"""

from chameleon.core.tools.base import Tool, ToolContext, ToolResult

__all__ = [
    "Tool",
    "ToolContext",
    "ToolResult",
]
