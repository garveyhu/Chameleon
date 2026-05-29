"""AggregatorNode —— 变量聚合节点（对齐 Dify Variable Aggregator）

把多个变量引用收集成一个干净的输出 dict，用于分支/多节点 fan-in 后归拢。

data.fields: dict[str, str]，每个 value 是带 {{#...#}} 引用的模板，如
    {"city": "{{#kb1.query#}}", "ctx": "{{#kb1.joined_context#}}"}
输出即解析后的 {key: text} dict。
"""

from __future__ import annotations

from typing import Any

from chameleon.engine.graph.context import NodeContext
from chameleon.engine.graph.node_base import Node
from chameleon.engine.graph.registry import register_node_type
from chameleon.engine.graph.variables import resolve_in_text


class AggregatorNode(Node[Any, dict]):
    """变量聚合节点（type='aggregator'）"""

    type = "aggregator"

    def validate_data(self, data: dict[str, Any]) -> None:
        fields = data.get("fields")
        if not isinstance(fields, dict) or not fields:
            raise ValueError("AggregatorNode.data.fields 必填（非空 dict[str,str]）")
        if not all(isinstance(v, str) for v in fields.values()):
            raise ValueError("AggregatorNode.data.fields 的值必须是字符串模板")

    async def execute(self, ctx: NodeContext, input: Any) -> dict:
        node_vars = (ctx.extra or {}).get("__vars__") or {}
        fields: dict[str, str] = self.spec.data.get("fields") or {}
        return {k: resolve_in_text(v, node_vars) for k, v in fields.items()}


register_node_type(AggregatorNode)
