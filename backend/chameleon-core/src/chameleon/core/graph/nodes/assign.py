"""AssignNode —— 会话变量赋值（P5-2，对齐 Dify Variable Assigner）

把 data.assignments（{变量名: 模板}）解析后输出为 dict；GraphProvider 把 assign 节点
的输出收集为「会话变量更新」，回传给客户端跨轮携带，使 {{#conversation.x#}} 可记住。

data.assignments: {"user_name": "{{#sys.query#}}", "count": "{{#conversation.count#}}1"}
"""

from __future__ import annotations

from typing import Any

from chameleon.core.graph.context import NodeContext
from chameleon.core.graph.node_base import Node
from chameleon.core.graph.registry import register_node_type
from chameleon.core.graph.variables import resolve_in_text


class AssignNode(Node[Any, dict]):
    """会话变量赋值节点（type='assign'）"""

    type = "assign"

    def validate_data(self, data: dict[str, Any]) -> None:
        a = data.get("assignments")
        if not isinstance(a, dict) or not a:
            raise ValueError("AssignNode.data.assignments 必填（非空 dict[str,str]）")
        if not all(isinstance(v, str) for v in a.values()):
            raise ValueError("AssignNode.data.assignments 的值必须是字符串模板")

    async def execute(self, ctx: NodeContext, input: Any) -> dict:
        node_vars = (ctx.extra or {}).get("__vars__") or {}
        assignments: dict[str, str] = self.spec.data.get("assignments") or {}
        return {k: resolve_in_text(v, node_vars) for k, v in assignments.items()}


register_node_type(AssignNode)
