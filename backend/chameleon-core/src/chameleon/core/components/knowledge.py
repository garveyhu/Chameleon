"""in-process 知识库 API（给本地 agent 用）

agent 子包只能依赖 chameleon-core，所以这里提供薄壳读 API。
所有 HTTP 路径（modules/knowledge）也复用这套——保证单一数据路径。

公开函数：
  await search_kb(kb_key, query, top_k=..., min_score=...) -> list[ChunkHit]
  await get_kb_meta(kb_key) -> KbMeta | None
"""

from __future__ import annotations

from dataclasses import dataclass

from loguru import logger
from sqlalchemy import select

from chameleon.core.api.exceptions import KnowledgeBaseNotFoundError
from chameleon.core.config import inventory
from chameleon.core.embedding import get_embedding_client
from chameleon.core.vector import ChunkHit
from chameleon.data.infra.db import AsyncSessionLocal
from chameleon.data.models import Agent, AgentKbLink, KnowledgeBase
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
    """语义检索 kb

    flow:
      kb_key → KbMeta → embed(query) → vector.search → list[ChunkHit]
    """
    meta = await get_kb_meta(kb_key)
    if meta is None:
        raise KnowledgeBaseNotFoundError(message=f"知识库不存在: {kb_key}")

    k = top_k or inventory.kb_default_top_k()
    client = get_embedding_client(meta.embedding_model)
    vecs = await client.embed([query])
    if not vecs:
        return []

    store = get_store()
    hits = await store.search(
        kb_id=meta.id,
        query_vec=vecs[0],
        top_k=k,
        min_score=min_score,
    )
    logger.debug(
        "search_kb | kb={} | query_len={} | top_k={} | hits={}",
        kb_key,
        len(query),
        k,
        len(hits),
    )
    return hits
