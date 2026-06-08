"""ClassifierNode —— LLM 意图分类（对齐 Dify Question Classifier）

把用户问题分到 data.categories 之一，输出 {category, raw}。下游用 if_else 读
{{#本节点id.category#}} 做分流（保持单出边，不引入动态 handle）。
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from chameleon.engine.graph.context import NodeContext
from chameleon.engine.graph.node_base import Node
from chameleon.engine.graph.registry import register_node_type

_QUERY_KEYS = ("query", "question", "input", "text", "answer")


def _pick_query(input: Any, sys_vars: dict[str, Any]) -> str:
    if isinstance(input, str) and input.strip():
        return input
    if isinstance(input, dict):
        for k in _QUERY_KEYS:
            v = input.get(k)
            if isinstance(v, str) and v.strip():
                return v
    sq = sys_vars.get("query")
    return sq if isinstance(sq, str) else ""


class ClassifierNode(Node[Any, dict]):
    """意图分类节点（type='classifier'）"""

    type = "classifier"

    def validate_data(self, data: dict[str, Any]) -> None:
        cats = data.get("categories")
        if not isinstance(cats, list) or len(cats) < 2:
            raise ValueError("ClassifierNode.data.categories 至少 2 个")
        if not all(isinstance(c, dict) and c.get("key") for c in cats):
            raise ValueError("每个 category 需含 key（可选 description）")

    async def execute(self, ctx: NodeContext, input: Any) -> dict:
        from chameleon.aikit.tasks.graph import classify

        node_vars = (ctx.extra or {}).get("__vars__") or {}
        query = _pick_query(input, node_vars.get("sys") or {})
        result = await classify(
            query,
            self.spec.data["categories"],
            model=self.spec.data.get("model_name"),
        )
        logger.debug(
            "ClassifierNode {} | raw={!r} | chosen={}",
            self.id,
            result["raw"],
            result["category"],
        )
        return result


register_node_type(ClassifierNode)
