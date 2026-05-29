"""TemplateNode —— 纯文本模板节点（变量组合，无 LLM）

把 data.template 里的 {{#sys.query#}} / {{#nodeId.field#}} 引用解析成文本，
输出 {"text": <rendered>}。用于拼 prompt 上下文 / 组装多节点输出 / 格式化。
"""

from __future__ import annotations

from typing import Any

from chameleon.engine.graph.context import NodeContext
from chameleon.engine.graph.node_base import Node
from chameleon.engine.graph.registry import register_node_type
from chameleon.engine.graph.variables import resolve_in_text


class TemplateNode(Node[Any, dict]):
    """文本模板节点（type='template'）"""

    type = "template"

    def validate_data(self, data: dict[str, Any]) -> None:
        if not isinstance(data.get("template"), str):
            raise ValueError("TemplateNode.data.template 必填（string）")

    async def execute(self, ctx: NodeContext, input: Any) -> dict:
        node_vars = (ctx.extra or {}).get("__vars__") or {}
        text = resolve_in_text(self.spec.data.get("template") or "", node_vars)
        return {"text": text}


register_node_type(TemplateNode)
