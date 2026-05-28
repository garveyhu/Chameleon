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
        sys_vars = node_vars.get("sys") or {}
        # Phase D：把本次 sys.attachments 透到节点输出（GraphProvider 会把它带到响应里）
        attachments = sys_vars.get("attachments") or []
        extras: dict[str, Any] = {}
        if attachments and self.spec.data.get("include_attachments", True):
            extras["attachments"] = attachments

        tmpl = self.spec.data.get("answer")
        if isinstance(tmpl, str) and tmpl.strip():
            return {"answer": resolve_in_text(tmpl, node_vars), **extras}

        # 无模板：透传上游
        if isinstance(input, dict):
            for key in ("answer", "text", "result", "output", "content"):
                v = input.get(key)
                if isinstance(v, str) and v.strip():
                    return {"answer": v, **extras}
            return {"answer": json.dumps(input, ensure_ascii=False, default=str), **extras}
        if isinstance(input, str):
            return {"answer": input, **extras}
        return {"answer": "" if input is None else str(input), **extras}


register_node_type(AnswerNode)
