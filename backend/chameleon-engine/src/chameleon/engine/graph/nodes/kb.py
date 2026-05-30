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

from chameleon.engine.graph.context import NodeContext
from chameleon.engine.graph.node_base import Node
from chameleon.engine.graph.registry import register_node_type


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
        # Phase D：use_ephemeral_kb=True 时不强制 kb_key（运行时按 session 找临时 KB）
        if data.get("use_ephemeral_kb"):
            return
        kb_key = data.get("kb_key")
        if not kb_key or not isinstance(kb_key, str):
            raise ValueError("KBNode.data.kb_key 必填（string；或开启 use_ephemeral_kb）")

    async def execute(self, ctx: NodeContext, input: Any) -> dict:
        # lazy import 避免 chameleon-core 在 import 时反向依赖 chameleon-api
        from chameleon.integrations.components.inventory import search_kb

        use_eph = bool(self.spec.data.get("use_ephemeral_kb"))
        kb_key = self.spec.data.get("kb_key") or ""
        top_k = int(self.spec.data.get("top_k") or 5)
        min_score = float(self.spec.data.get("min_score") or 0.0)
        separator = self.spec.data.get("context_separator") or "\n\n"

        # P4：input 里没有 query 时回退 sys.query（KB 不在 start 之后也能检索对话问题）
        try:
            query = _pick_query(input)
        except ValueError:
            sys_q = ((ctx.extra or {}).get("__vars__", {}).get("sys") or {}).get(
                "query"
            )
            if not isinstance(sys_q, str) or not sys_q.strip():
                raise
            query = sys_q

        # Phase D 临时 KB 模式：按 session_id 查 ephemeral_kb 顶替 kb_key
        if use_eph:
            session_id = (
                (ctx.extra or {}).get("__vars__", {}).get("sys", {}).get("session_id")
            )
            # session_id 也可能直接在 ctx；fallback 没有时落空 hits
            if not session_id:

                session_id = getattr(ctx, "session_id", None)
            eph_kb_key = await _resolve_ephemeral_kb_key(session_id) if session_id else None
            if not eph_kb_key:
                logger.debug("KBNode {} 临时 KB 模式但 session 无附件 KB，返空", self.id)
                return {
                    "query": query,
                    "hits": [],
                    "joined_context": "",
                    "top_k": top_k,
                }
            kb_key = eph_kb_key

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


async def _resolve_ephemeral_kb_key(session_id: str) -> str | None:
    """按 session_id 找 ephemeral KB 的 kb_key（独立 AsyncSession 短查询）"""
    from sqlalchemy import select

    from chameleon.data.infra.db import AsyncSessionLocal
    from chameleon.data.models import KnowledgeBase, SessionFile

    async with AsyncSessionLocal() as db:
        kb_id = (
            await db.execute(
                select(SessionFile.ephemeral_kb_id)
                .where(
                    SessionFile.session_id == session_id,
                    SessionFile.deleted_at.is_(None),
                    SessionFile.status == "ready",
                    SessionFile.ephemeral_kb_id.is_not(None),
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        if not kb_id:
            return None
        kb = await db.get(KnowledgeBase, kb_id)
        if kb is None or kb.deleted_at is not None:
            return None
        return kb.kb_key


register_node_type(KBNode)
