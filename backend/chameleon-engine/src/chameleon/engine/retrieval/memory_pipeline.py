"""agentkit 语义记忆的 embed + hybrid 召回实现 —— T1-1 memory 升级 M1。

复用 KB 检索栈的积木（不重造）：`get_embedding_client` 出向量、`HybridPipeline` 做
vector+BM25 RRF 融合、`build_reranker` 可选重排。镜像 [[pipeline]] 的 recall 构造，
但召回目标是 `agent_memory_vector`（按 agent_key+scope_ref 隔离），不是 KB chunks。

经 `providers.base.memory_vector_bridge` 注入给 providers-local 的 InProcessTransport
（agentkit/providers 不反依赖 engine，同 wire_retrieval_bridge 的反转）。

红线：scope 隔离硬约束 —— 所有召回 / 索引都带 (agent_key, scope_ref) 过滤，绝不串号。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from loguru import logger
from sqlalchemy import func, literal_column, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.config.inventory import case_embedding
from chameleon.core.config.json_settings import chameleon_settings
from chameleon.data.utils import tokenizer
from chameleon.engine.retrieval.hybrid import Hit, HybridConfig, HybridPipeline
from chameleon.integrations.embedding import get_embedding_client

RecallFn = Callable[[str, int], Awaitable[list[Hit]]]


# ── 召回构造（镜像 pipeline._build_*_recall，目标换成 agent_memory_vector） ──


def _build_vector_recall(
    session: AsyncSession, agent_key: str, scope_ref: str
) -> RecallFn:
    async def recall(query: str, n: int) -> list[Hit]:
        from chameleon.data.models import AgentMemoryVector

        model = case_embedding()
        if not model:
            return []  # 无默认 embedding 模型 → 仅 BM25 路
        client = get_embedding_client(model)
        vecs = await client.embed([query])
        if not vecs:
            return []
        distance = AgentMemoryVector.embedding.cosine_distance(vecs[0]).label(
            "distance"
        )
        stmt = (
            select(
                AgentMemoryVector.id,
                AgentMemoryVector.mkey,
                AgentMemoryVector.text,
                distance,
            )
            .where(
                AgentMemoryVector.agent_key == agent_key,
                AgentMemoryVector.scope_ref == scope_ref,
            )
            .order_by(distance.asc())
            .limit(n)
        )
        rows = (await session.execute(stmt)).all()
        return [
            Hit(
                chunk_id=r.id,
                content=r.text,
                score=1.0 - float(r.distance),
                meta={"mkey": r.mkey},
            )
            for r in rows
        ]

    return recall


def _build_keyword_recall(
    session: AsyncSession, agent_key: str, scope_ref: str
) -> RecallFn:
    async def recall(query: str, n: int) -> list[Hit]:
        from chameleon.data.models import AgentMemoryVector

        terms = tokenizer.keyword_query_terms(query)
        if not terms:
            return []
        ts_query = func.to_tsquery("simple", " | ".join(terms))
        tsv_col = literal_column("content_tsv")
        rank = func.ts_rank(tsv_col, ts_query).label("rank")
        stmt = (
            select(
                AgentMemoryVector.id,
                AgentMemoryVector.mkey,
                AgentMemoryVector.text,
                rank,
            )
            .where(
                AgentMemoryVector.agent_key == agent_key,
                AgentMemoryVector.scope_ref == scope_ref,
                tsv_col.op("@@")(ts_query),
            )
            .order_by(rank.desc())
            .limit(n)
        )
        rows = (await session.execute(stmt)).all()
        if not rows:
            return []
        max_rank = max(float(r.rank) for r in rows) or 1.0
        return [
            Hit(
                chunk_id=r.id,
                content=r.text,
                score=float(r.rank) / max_rank,
                meta={"mkey": r.mkey},
            )
            for r in rows
        ]

    return recall


def _build_memory_reranker():  # noqa: ANN202
    """memory 召回的可选重排（复用 build_reranker）。配置走 agentkit.memory.reranker，
    默认关（与 KB rerank 默认跟随配置同纪律——无 rerank 模型时不强开）。"""
    cfg = chameleon_settings.get("agentkit.memory.reranker")
    if not cfg:
        return None
    try:
        from chameleon.engine.retrieval.rerankers import build_reranker

        return build_reranker(cfg)
    except (ValueError, ImportError):
        logger.warning("memory reranker 配置无效，跳过 rerank")
        return None


# ── 桥注入的两个 fn ────────────────────────────────────────


async def _index(agent_key: str, scope_ref: str, mkey: str, text: str) -> None:
    """embed + upsert 一条记忆向量行；text 空 → 删除该行（值被清空时同步）。"""
    from chameleon.data.infra.db import AsyncSessionLocal
    from chameleon.data.models import AgentMemoryVector

    text = (text or "").strip()

    def _q():  # noqa: ANN202
        return select(AgentMemoryVector).where(
            AgentMemoryVector.agent_key == agent_key,
            AgentMemoryVector.scope_ref == scope_ref,
            AgentMemoryVector.mkey == mkey,
        )

    async with AsyncSessionLocal() as s:
        existing = (await s.execute(_q())).scalar_one_or_none()
        if not text:
            if existing is not None:
                await s.delete(existing)
                await s.commit()
            return
        model = case_embedding()
        if not model:
            logger.warning("memory 向量索引跳过：无默认 embedding 模型（cases.embedding）")
            return
        vecs = await get_embedding_client(model).embed([text])
        if not vecs:
            return
        emb = vecs[0]
        text_search = tokenizer.segment_for_index(text)
        if existing is None:
            s.add(
                AgentMemoryVector(
                    agent_key=agent_key,
                    scope_ref=scope_ref,
                    mkey=mkey,
                    text=text,
                    text_search=text_search,
                    embedding=emb,
                )
            )
        else:
            existing.text = text
            existing.text_search = text_search
            existing.embedding = emb
        try:
            await s.commit()
        except IntegrityError:
            # 并发：另一事务已 insert 同 (agent_key,scope_ref,mkey)（uq）→ 回滚改 update。
            await s.rollback()
            row = (await s.execute(_q())).scalar_one_or_none()
            if row is None:
                raise
            row.text = text
            row.text_search = text_search
            row.embedding = emb
            await s.commit()


async def _search(
    agent_key: str,
    scope_ref: str,
    query: str,
    *,
    top_k: int = 5,
    min_score: float = 0.0,
) -> list[dict]:
    """按 (agent_key, scope_ref) 隔离做 vector+BM25 hybrid 召回（+可选 rerank）。"""
    from chameleon.data.infra.db import AsyncSessionLocal

    if not query or not query.strip():
        return []
    async with AsyncSessionLocal() as s:
        pipeline = HybridPipeline(
            vector_recall=_build_vector_recall(s, agent_key, scope_ref),
            keyword_recall=_build_keyword_recall(s, agent_key, scope_ref),
            config=HybridConfig(
                top_k=top_k, min_score=min_score, allow_kinds={"text"}
            ),
            reranker=_build_memory_reranker(),
        )
        hits = await pipeline.run(query)
    return [
        {"key": (h.meta or {}).get("mkey"), "text": h.content, "score": h.score}
        for h in hits
        if (h.meta or {}).get("mkey")
    ]


def wire_memory_vector_bridge() -> None:
    """app 启动注入 memory 语义召回 fn 到 providers-base 的 IoC 桥。

    让 agentkit ctx.memory.search/set（providers-local，不依赖 engine）用上
    embed + hybrid 召回。未注入则 memory 仅 KV。
    """
    from chameleon.providers.base.memory_vector_bridge import (
        set_memory_index_fn,
        set_memory_search_fn,
    )

    set_memory_index_fn(_index)
    set_memory_search_fn(_search)
