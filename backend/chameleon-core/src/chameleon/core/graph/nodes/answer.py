"""AnswerNode —— 显式「最终回答」节点（P5-3）

标记 graph 的最终回答来源。data.answer 是带 {{#...#}} 引用的模板（如
"{{#chat.answer#}}"）；为空则透传上游 input 的 answer/文本。输出 {"answer": <text>}。
GraphProvider 优先把 answer 节点的输出当作 agent 回答。
"""

from __future__ import annotations

import json
from typing import Any

from chameleon.core.graph.context import NodeContext
from chameleon.core.graph.node_base import Node
from chameleon.core.graph.registry import register_node_type
from chameleon.core.graph.variables import resolve_in_text


class AnswerNode(Node[Any, dict]):
    """显式最终回答节点（type='answer'）"""

    type = "answer"

    async def execute(self, ctx: NodeContext, input: Any) -> dict:
        node_vars = (ctx.extra or {}).get("__vars__") or {}
        tmpl = self.spec.data.get("answer")
        if isinstance(tmpl, str) and tmpl.strip():
            return {"answer": resolve_in_text(tmpl, node_vars)}

        # 无模板：透传上游
        if isinstance(input, dict):
            for key in ("answer", "text", "result", "output", "content"):
                v = input.get(key)
                if isinstance(v, str) and v.strip():
                    return {"answer": v}
            return {"answer": json.dumps(input, ensure_ascii=False, default=str)}
        if isinstance(input, str):
            return {"answer": input}
        return {"answer": "" if input is None else str(input)}


register_node_type(AnswerNode)
