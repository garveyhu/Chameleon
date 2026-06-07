"""ToolNode —— 调注册的 Tool（P18.2 起接 chameleon.core.tools 实现）

执行逻辑（`run_tool`）已下沉到 `chameleon.integrations.tools.execute`，与 graph
解耦，graph ToolNode / LLMNode function-calling / agentkit 共用同一入口。本模块只
保留 graph 节点壳 + 兼容 re-export。

data 配置（v0.4 起）：
    {
      "tool_key": "http",
      "args": { ... }       # 透传给 Tool.run；也可以从上游 input 拼
    }

兼容：register_tool() / run_tool 本地也透出，方便测试 / 早期模块手动 import。
"""

from __future__ import annotations

from typing import Any

from chameleon.engine.graph.context import NodeContext
from chameleon.engine.graph.node_base import Node
from chameleon.engine.graph.registry import register_node_type
from chameleon.integrations.tools import (
    get_tool_class,  # noqa: F401  (compat re-export)
    run_tool,  # noqa: F401  (compat re-export)
)
from chameleon.integrations.tools import (
    register_tool as _register_tool_real,
)


def register_tool(tool_cls):  # noqa: ANN001
    """转发到 chameleon.integrations.tools.registry.register_tool

    兼容老测试 / 早期代码直接从本模块 import register_tool 的写法。
    """
    return _register_tool_real(tool_cls)


class ToolNode(Node[Any, dict]):
    """调注册 Tool"""

    type = "tool"

    def validate_data(self, data: dict[str, Any]) -> None:
        tk = data.get("tool_key")
        if not tk or not isinstance(tk, str):
            raise ValueError("ToolNode.data.tool_key 必填（string）")

    async def execute(self, ctx: NodeContext, input: Any) -> dict:
        tk = self.spec.data["tool_key"]

        args = dict(self.spec.data.get("args") or {})
        if isinstance(input, dict):
            # input 字段被 data.args 覆盖（admin 优先）
            args = {**input, **args}

        return await run_tool(
            tk,
            args,
            caller="graph",
            related_id=str(ctx.graph_run_id),
            extra={"graph_id": ctx.graph_id, "node_id": self.id},
            config_override=self.spec.data.get("config"),
        )


register_node_type(ToolNode)
