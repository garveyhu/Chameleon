"""KBNode —— 调 KB 检索取 top_k chunks

data 配置：
    {
      "kb_key": "smoke",
      "top_k": 5,
      "min_score": 0.0,
      "context_separator": "\\n\\n",
    }

input:
    {"query": "..."}  或者上游 LLMNode 传 {"answer": "..."} 都接受；
    取 first string-typed field 作 query。

output:
    {
      "query": "...",
      "hits": [{"id", "doc_id", "seq", "content", "score"}, ...],
      "joined_context": "h1.content\n\nh2.content",
      "top_k": 5,
    }
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from chameleon.core.graph.context import NodeContext
from chameleon.core.graph.registry import register_node_type
from chameleon.core.graph.node_base import Node


def _pick_query(input: Any) -> str:
    """从异构 input 里挑一个 string 当 query"""
    if isinstance(input, str):
        return input
    if isinstance(input, dict):
        for key in ("query", "question", "input", "text", "answer"):
            v = input.get(key)
            if isinstance(v, str) and v.strip():
                return v
        # fallback：任意第一个非空字符串字段
        for v in input.values():
            if isinstance(v, str) and v.strip():
                return v
    raise ValueError(f"KBNode 无法从 input 提取 query：{type(input).__name__}")


class KBNode(Node[Any, dict]):
    """KB 检索节点

    spec.data 必填 kb_key；top_k / min_score / context_separator 可选。
    """

    type = "kb"

    def validate_data(self, data: dict[str, Any]) -> None:
        kb_key = data.get("kb_key")
        if not kb_key or not isinstance(kb_key, str):
            raise ValueError("KBNode.data.kb_key 必填（string）")

    async def execute(self, ctx: NodeContext, input: Any) -> dict:
        # lazy import 避免 chameleon-core 在 import 时反向依赖 chameleon-api
        from chameleon.core.components.inventory import search_kb

        kb_key = self.spec.data["kb_key"]
        top_k = int(self.spec.data.get("top_k") or 5)
        min_score = float(self.spec.data.get("min_score") or 0.0)
        separator = self.spec.data.get("context_separator") or "\n\n"

        query = _pick_query(input)

        hits = await search_kb(
            kb_key, query, top_k=top_k, min_score=min_score
        )

        joined = separator.join(h.content for h in hits)

        logger.debug(
            "KBNode {} | kb={} | top_k={} | hits={}",
            self.id,
            kb_key,
            top_k,
            len(hits),
        )

        return {
            "query": query,
            "hits": [
                {
                    "id": h.id,
                    "doc_id": h.doc_id,
                    "seq": h.seq,
                    "content": h.content,
                    "score": h.score,
                }
                for h in hits
            ],
            "joined_context": joined,
            "top_k": top_k,
        }


register_node_type(KBNode)
