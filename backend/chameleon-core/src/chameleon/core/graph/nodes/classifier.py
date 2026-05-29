"""ClassifierNode —— LLM 意图分类（对齐 Dify Question Classifier）

把用户问题分到 data.categories 之一，输出 {category, raw}。下游用 if_else 读
{{#本节点id.category#}} 做分流（保持单出边，不引入动态 handle）。
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from chameleon.core.graph.context import NodeContext
from chameleon.core.graph.node_base import Node
from chameleon.core.graph.registry import register_node_type

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
        from langchain_core.messages import HumanMessage, SystemMessage

        from chameleon.integrations.llms.factory import resolve_llm

        node_vars = (ctx.extra or {}).get("__vars__") or {}
        query = _pick_query(input, node_vars.get("sys") or {})
        cats = self.spec.data["categories"]
        keys = [str(c["key"]) for c in cats]
        cat_lines = "\n".join(
            f"- {c['key']}: {c.get('description', '')}" for c in cats
        )
        prompt = (
            f"把用户问题分到下列类别之一，只输出类别 key（{' / '.join(keys)}）：\n"
            f"{cat_lines}\n\n问题：{query}"
        )
        client = await resolve_llm(self.spec.data.get("model_name"))
        ai = await client.ainvoke(
            [
                SystemMessage(content="你是意图分类器，只输出一个类别 key，不要多余文字。"),
                HumanMessage(content=prompt),
            ]
        )
        raw = (ai.content if hasattr(ai, "content") else str(ai)).strip()
        chosen = (
            next((k for k in keys if k == raw), None)
            or next((k for k in keys if k in raw), None)
            or keys[0]
        )
        logger.debug("ClassifierNode {} | raw={!r} | chosen={}", self.id, raw, chosen)
        return {"category": chosen, "raw": raw}


register_node_type(ClassifierNode)
