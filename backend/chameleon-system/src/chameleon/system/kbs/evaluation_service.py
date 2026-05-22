"""KB 检索评估服务

评估批次生命周期：
    pending → running → done / failed

输入 queries：[{query, expected_chunk_ids: [int]}]
输出 results：
    {
      "hit_at_k": {"1": 0.5, "3": 0.75, "5": 0.9},
      "mrr": 0.65,
      "latency_p50_ms": 45.2,
      "latency_p95_ms": 132.0,
      "per_query": [
        {"query": "...", "hits": [chunk_ids], "expected": [...], "first_hit_rank": 2, "latency_ms": 38.4}
      ]
    }
"""

from __future__ import annotations

import asyncio
import statistics
import time
from datetime import datetime, timezone

from loguru import logger
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.api.exceptions import (
    BusinessError,
    ResultCode,
    ValidationError,
)
from chameleon.core.api.response import PageParams, PageResult
from chameleon.core.infra.db import AsyncSessionLocal
from chameleon.core.models import KnowledgeBase, RetrievalEvaluation
from chameleon.system.kbs.document_service import search_chunks

# ── CRUD ──────────────────────────────────────────────────


async def _get_kb(session: AsyncSession, kb_id: int) -> KnowledgeBase:
    kb = (
        await session.execute(
            select(KnowledgeBase).where(
                KnowledgeBase.id == kb_id, KnowledgeBase.deleted_at.is_(None)
            )
        )
    ).scalar_one_or_none()
    if kb is None:
        raise BusinessError(
            ResultCode.KnowledgeBaseNotFound, message=f"kb 不存在: {kb_id}"
        )
    return kb


async def create_evaluation(
    session: AsyncSession,
    *,
    kb_id: int,
    name: str,
    queries: list[dict],
    recall_mode: str = "vector",
    top_k: int = 5,
) -> RetrievalEvaluation:
    if not queries:
        raise ValidationError(message="queries 不能为空")
    if recall_mode not in ("vector", "keyword", "hybrid"):
        raise ValidationError(message=f"unsupported recall_mode: {recall_mode}")
    for q in queries:
        if not q.get("query"):
            raise ValidationError(message="每条 query 必须有 query 字段")
        if "expected_chunk_ids" not in q:
            raise ValidationError(
                message="每条 query 必须有 expected_chunk_ids 列表"
            )

    await _get_kb(session, kb_id)
    row = RetrievalEvaluation(
        kb_id=kb_id,
        name=name,
        queries=queries,
        recall_mode=recall_mode,
        top_k=top_k,
        status="pending",
    )
    session.add(row)
    await session.flush()
    return row


async def list_evaluations(
    session: AsyncSession, *, kb_id: int, page: PageParams
) -> PageResult[RetrievalEvaluation]:
    stmt = select(RetrievalEvaluation).where(
        RetrievalEvaluation.kb_id == kb_id
    )
    total = (
        await session.execute(select(func.count()).select_from(stmt.subquery()))
    ).scalar_one()
    rows = (
        (
            await session.execute(
                stmt.order_by(desc(RetrievalEvaluation.created_at))
                .offset(page.offset)
                .limit(page.limit)
            )
        )
        .scalars()
        .all()
    )
    return PageResult(
        items=list(rows), total=total, page=page.page, page_size=page.page_size
    )


async def get_evaluation(
    session: AsyncSession, *, kb_id: int, eval_id: int
) -> RetrievalEvaluation:
    row = (
        await session.execute(
            select(RetrievalEvaluation).where(
                RetrievalEvaluation.id == eval_id,
                RetrievalEvaluation.kb_id == kb_id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise BusinessError(
            ResultCode.Fail, message=f"评估批次不存在: {eval_id}"
        )
    return row


async def delete_evaluation(
    session: AsyncSession, *, kb_id: int, eval_id: int
) -> RetrievalEvaluation:
    row = await get_evaluation(session, kb_id=kb_id, eval_id=eval_id)
    await session.delete(row)
    return row


# ── async worker ──────────────────────────────────────────


def spawn_eval(eval_id: int, kb_id: int) -> None:
    asyncio.create_task(run_evaluation(eval_id=eval_id, kb_id=kb_id))


async def run_evaluation(*, eval_id: int, kb_id: int) -> None:
    """异步评估：跑批 → 算 hit@k / MRR / latency → 回写 results"""
    logger.info("eval worker start | eval={} | kb={}", eval_id, kb_id)
    try:
        async with AsyncSessionLocal() as session:
            row = await get_evaluation(session, kb_id=kb_id, eval_id=eval_id)
            row.status = "running"
            await session.commit()

        # 拉评估配置
        async with AsyncSessionLocal() as session:
            row = await get_evaluation(session, kb_id=kb_id, eval_id=eval_id)
            queries = row.queries
            top_k = row.top_k
            mode = row.recall_mode

        per_query: list[dict] = []
        latencies: list[float] = []
        for q in queries:
            qtext = q["query"]
            expected = set(int(x) for x in (q.get("expected_chunk_ids") or []))
            t0 = time.perf_counter()
            async with AsyncSessionLocal() as session:
                hits = await search_chunks(
                    session,
                    kb_id=kb_id,
                    query=qtext,
                    top_k=top_k,
                    mode=mode,
                )
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            latencies.append(elapsed_ms)
            hit_ids = [h["chunk_id"] for h in hits]
            # first_hit_rank：1-based；未命中 = None
            first_rank: int | None = None
            for idx, cid in enumerate(hit_ids):
                if cid in expected:
                    first_rank = idx + 1
                    break
            per_query.append(
                {
                    "query": qtext,
                    "hits": hit_ids,
                    "expected": sorted(expected),
                    "first_hit_rank": first_rank,
                    "latency_ms": round(elapsed_ms, 1),
                }
            )

        total = len(per_query)
        ks = [1, 3, 5]
        if top_k > 5:
            ks.append(top_k)
        hit_at_k: dict[str, float] = {}
        rr_sum = 0.0
        for k in ks:
            n = sum(
                1
                for pq in per_query
                if pq["first_hit_rank"] is not None and pq["first_hit_rank"] <= k
            )
            hit_at_k[str(k)] = round(n / total, 4) if total else 0.0
        for pq in per_query:
            if pq["first_hit_rank"]:
                rr_sum += 1.0 / pq["first_hit_rank"]
        mrr = round(rr_sum / total, 4) if total else 0.0

        results = {
            "hit_at_k": hit_at_k,
            "mrr": mrr,
            "latency_p50_ms": round(statistics.median(latencies), 1)
            if latencies
            else 0.0,
            "latency_p95_ms": round(_p95(latencies), 1) if latencies else 0.0,
            "per_query": per_query,
        }

        async with AsyncSessionLocal() as session:
            row = await get_evaluation(session, kb_id=kb_id, eval_id=eval_id)
            row.results = results
            row.status = "done"
            row.completed_at = datetime.now(timezone.utc)
            await session.commit()
        logger.info(
            "eval worker done | eval={} | hit@5={} | mrr={}",
            eval_id,
            hit_at_k.get("5"),
            mrr,
        )
    except Exception as e:  # noqa: BLE001
        logger.exception("eval worker failed | eval={}", eval_id)
        async with AsyncSessionLocal() as session:
            try:
                row = await get_evaluation(session, kb_id=kb_id, eval_id=eval_id)
                row.status = "failed"
                row.error_message = str(e)[:500]
                row.completed_at = datetime.now(timezone.utc)
                await session.commit()
            except Exception:
                logger.exception("eval failure finalize itself failed")


def _p95(samples: list[float]) -> float:
    if not samples:
        return 0.0
    s = sorted(samples)
    idx = max(0, min(len(s) - 1, int(round(0.95 * (len(s) - 1)))))
    return s[idx]
