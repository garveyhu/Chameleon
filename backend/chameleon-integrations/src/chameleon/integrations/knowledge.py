"""in-process 知识库检索实现（带 DB 访问的检索编排）

属 integrations 层：依赖 core（协议/配置/embedding/exceptions）+ data（持久化）+
integrations.vector（向量存储实现）。所有 HTTP 路径（api/knowledge）也复用这套——
保证单一数据路径。

公开函数：
  await search_kb(kb_key, query, top_k=..., min_score=...) -> list[ChunkHit]
  await get_kb_meta(kb_key) -> KbMeta | None
  await list_linked_kb_metas(agent_key) -> list[KbMeta]
"""

from __future__ import annotations

from dataclasses import dataclass

from loguru import logger
from sqlalchemy import select

from chameleon.core.api.exceptions import KnowledgeBaseNotFoundError
from chameleon.core.config import inventory
from chameleon.core.vector import ChunkHit
from chameleon.data.infra.db import AsyncSessionLocal
from chameleon.data.models import Agent, AgentKbLink, KnowledgeBase
from chameleon.integrations.embedding import get_embedding_client
from chameleon.integrations.vector import get_store


@dataclass(frozen=True)
class KbMeta:
    id: int
    kb_key: str
    name: str
    description: str | None
    embedding_model: str
    embedding_dim: int
    chunk_size: int
    chunk_overlap: int


async def get_kb_meta(kb_key: str) -> KbMeta | None:
    async with AsyncSessionLocal() as session:
        row = (
            await session.execute(
                select(KnowledgeBase).where(
                    KnowledgeBase.kb_key == kb_key,
                    KnowledgeBase.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        return KbMeta(
            id=row.id,
            kb_key=row.kb_key,
            name=row.name,
            description=row.description,
            embedding_model=row.embedding_model,
            embedding_dim=row.embedding_dim,
            chunk_size=row.chunk_size,
            chunk_overlap=row.chunk_overlap,
        )


async def list_linked_kb_metas(agent_key: str) -> list[KbMeta]:
    """返指定 agent 关联的全部 KB（按 agent_kb_link）。

    用于 BaseAgent.retrieve() 在 invoke 时跨 KB 检索。
    """
    async with AsyncSessionLocal() as session:
        rows = (
            (
                await session.execute(
                    select(KnowledgeBase)
                    .join(AgentKbLink, AgentKbLink.kb_id == KnowledgeBase.id)
                    .join(Agent, Agent.id == AgentKbLink.agent_id)
                    .where(
                        Agent.agent_key == agent_key,
                        Agent.deleted_at.is_(None),
                        KnowledgeBase.deleted_at.is_(None),
                    )
                )
            )
            .scalars()
            .all()
        )
    return [
        KbMeta(
            id=r.id,
            kb_key=r.kb_key,
            name=r.name,
            description=r.description,
            embedding_model=r.embedding_model,
            embedding_dim=r.embedding_dim,
            chunk_size=r.chunk_size,
            chunk_overlap=r.chunk_overlap,
        )
        for r in rows
    ]


async def search_kb(
    kb_key: str,
    query: str,
    *,
    top_k: int | None = None,
    min_score: float = 0.0,
) -> list[ChunkHit]:
    """语义检索 kb（自动落 retriever 观测节点）

    flow:
      kb_key → KbMeta → embed(query) → vector.search → list[ChunkHit]

    经 record_scope 切面自动出 retriever trace 节点（全调用路径覆盖：API / 嵌入式 /
    Playground / 工作流 / agentkit），无需调用方手写埋点。
    """
    from chameleon.core.observe.context import ObservationType
    from chameleon.integrations.observe.aspect import record_scope

    k = top_k or inventory.kb_default_top_k()
    async with record_scope(
        observation_type=ObservationType.RETRIEVER,
        name="search_kb",
        request_payload={
            "kb_key": kb_key,
            "query": query[:500],
            "top_k": k,
            "mode": "vector",
        },
    ) as scope:
        meta = await get_kb_meta(kb_key)
        if meta is None:
            raise KnowledgeBaseNotFoundError(message=f"知识库不存在: {kb_key}")

        client = get_embedding_client(meta.embedding_model)
        vecs = await client.embed([query])
        if not vecs:
            scope.response_payload = {"hit_count": 0, "citations": []}
            return []

        store = get_store()
        hits = await store.search(
            kb_id=meta.id,
            query_vec=vecs[0],
            top_k=k,
            min_score=min_score,
        )
        scope.response_payload = {
            "hit_count": len(hits),
            "citations": [
                {
                    "source": kb_key,
                    "ref": f"doc{h.doc_id}#{h.seq}",
                    "content": h.content[:300],
                    "score": round(h.score, 4),
                }
                for h in hits
            ],
        }
        logger.debug(
            "search_kb | kb={} | query_len={} | top_k={} | hits={}",
            kb_key,
            len(query),
            k,
            len(hits),
        )
        return hits
