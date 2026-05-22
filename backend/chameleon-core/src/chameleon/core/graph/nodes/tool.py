"""ToolNode —— 调注册的 Tool（P18.2 才有真实 Tool 实现）

data 配置：
    {
      "tool_key": "http",
      "args": { ... }       # 透传给 Tool.run；也可以从 input 拼
    }

P18.1（本 PR）：Tool 注册表还没建好，ToolNode 仅做 stub —— 检查 tool_key 已声明，
但执行时 raise NotImplementedError（带清晰指引）。

P18.2（PR #22-#23）：Tool 协议落地后，本节点改为真调 Tool.run(args, ctx)。
"""

from __future__ import annotations

from typing import Any

from chameleon.core.graph.context import NodeContext
from chameleon.core.graph.executor import register_node_type
from chameleon.core.graph.node_base import Node


# stub registry：现在为空，P18.2 改造时把 Tool 类塞进来
_TOOL_REGISTRY: dict[str, type] = {}


def register_tool(tool_cls) -> type:  # noqa: ANN001
    """P18.2 起：Tool 子类自注册入口"""
    key = getattr(tool_cls, "tool_key", None) or tool_cls.__name__
    _TOOL_REGISTRY[key] = tool_cls
    return tool_cls


class ToolNode(Node[Any, dict]):
    """调注册 Tool；P18.1 stub —— 报清晰 NotImplementedError"""

    type = "tool"

    def validate_data(self, data: dict[str, Any]) -> None:
        tk = data.get("tool_key")
        if not tk or not isinstance(tk, str):
            raise ValueError("ToolNode.data.tool_key 必填（string）")
        # P18.1 不强校验 tool 已注册（registry 空）；P18.2 会改为强校验

    async def execute(self, ctx: NodeContext, input: Any) -> dict:
        tk = self.spec.data["tool_key"]
        if tk not in _TOOL_REGISTRY:
            raise NotImplementedError(
                f"ToolNode tool_key={tk!r}：Tool 注册表为空 / 未注册；"
                f"P18.2 引入 chameleon.core.tools 后此节点才能跑。"
            )

        tool_cls = _TOOL_REGISTRY[tk]
        # P18.2 占位调用形态（实际签名以 P18.2 PR #22 为准）
        tool = tool_cls()
        args = self.spec.data.get("args") or {}
        if isinstance(input, dict):
            args = {**input, **args}
        result = await tool.run(args, ctx)
        return {"tool_key": tk, "result": result}


register_node_type(ToolNode)
