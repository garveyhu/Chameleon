"""检索召回质量基准 —— v1.1 PR B2

对比三种检索策略在同一组 (query, expected_chunk_ids) 上的召回质量：

  baseline      单 query 向量召回（对照组）
  multi_query   LLM 改写 N 个变体，各自向量召回后 RRF 融合（B1）
  hyde          LLM 生成假设性答案，用假答案向量召回（B2）

指标：hit@1 / hit@3 / hit@5 / MRR / 延迟 P50。输出一张对比表。

用法：
    python scripts/bench_retrieval.py --kb my-kb --queries eval.json
    python scripts/bench_retrieval.py --kb my-kb --eval-id 123   # 从已存评估批次取 query

eval.json 格式：
    [{"query": "...", "expected_chunk_ids": [1, 2]}, ...]

注意：本脚本需要可用的 embedding / LLM provider（model.json）+ 已 ingest 的 KB。
无 API key / 空 KB 时会逐 query 报错并跳过，不影响其它策略统计。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path

# 让 import chameleon 工作（与 scripts/bench_v1.py 一致）
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))


@dataclass
class EvalQuery:
    query: str
    expected: set[int]


# ── LLM 适配：langchain chat model → expander 的 complete_fn ──


def _make_complete_fn():
    from langchain_core.messages import HumanMessage

    from chameleon.core.components import llm

    async def complete(prompt: str) -> str:
        resp = await llm().ainvoke([HumanMessage(content=prompt)])
        content = resp.content
        return content if isinstance(content, str) else str(content)

    return complete


# ── 向量召回（real DB + embedding） ─────────────────────────


async def _vector_recall(
    *, kb_id: int, embedding_model: str, query: str, top_k: int
) -> list[int]:
    """返回命中的 chunk_id 有序列表（按相似度降序）"""
    from chameleon.core.embedding import get_embedding_client
    from chameleon.core.vector import get_store

    client = get_embedding_client(embedding_model)
    vecs = await client.embed([query])
    if not vecs:
        return []
    hits = await get_store().search(kb_id=kb_id, query_vec=vecs[0], top_k=top_k)
    return [h.id for h in hits]


# ── 策略 ────────────────────────────────────────────────────


async def _run_baseline(*, kb_id, embedding_model, query, top_k) -> list[int]:
    return await _vector_recall(
        kb_id=kb_id, embedding_model=embedding_model, query=query, top_k=top_k
    )


async def _run_multi_query(
    *, kb_id, embedding_model, query, top_k, complete_fn, n
) -> list[int]:
    from chameleon.core.retrieval import Hit, expand_queries, fuse_rrf_many

    variants = await expand_queries(query, complete_fn=complete_fn, n=n)
    ranked_lists: list[list[Hit]] = []
    for q in variants:
        ids = await _vector_recall(
            kb_id=kb_id,
            embedding_model=embedding_model,
            query=q,
            top_k=top_k * 2,
        )
        ranked_lists.append([Hit(chunk_id=cid) for cid in ids])
    fused = fuse_rrf_many(ranked_lists)
    return [h.chunk_id for h in fused[:top_k]]


async def _run_hyde(
    *, kb_id, embedding_model, query, top_k, complete_fn
) -> list[int]:
    from chameleon.core.retrieval import hyde_query

    hypo = await hyde_query(query, complete_fn=complete_fn)
    return await _vector_recall(
        kb_id=kb_id, embedding_model=embedding_model, query=hypo, top_k=top_k
    )


# ── 指标 ────────────────────────────────────────────────────


@dataclass
class StrategyStats:
    name: str
    hit_at: dict[int, float]
    mrr: float
    latency_p50_ms: float
    errors: int


def _first_hit_rank(hit_ids: list[int], expected: set[int]) -> int | None:
    for idx, cid in enumerate(hit_ids):
        if cid in expected:
            return idx + 1
    return None


def _aggregate(
    name: str, ranks: list[int | None], latencies: list[float], errors: int
) -> StrategyStats:
    total = len(ranks)
    ks = (1, 3, 5)
    hit_at = {
        k: round(sum(1 for r in ranks if r is not None and r <= k) / total, 4)
        if total
        else 0.0
        for k in ks
    }
    rr = sum(1.0 / r for r in ranks if r)
    mrr = round(rr / total, 4) if total else 0.0
    p50 = round(statistics.median(latencies), 1) if latencies else 0.0
    return StrategyStats(name, hit_at, mrr, p50, errors)


# ── 主流程 ──────────────────────────────────────────────────


def _load_queries_from_file(path: Path) -> list[EvalQuery]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [
        EvalQuery(
            query=item["query"],
            expected=set(int(x) for x in item.get("expected_chunk_ids") or []),
        )
        for item in raw
    ]


async def _load_queries_from_eval(kb_id: int, eval_id: int) -> list[EvalQuery]:
    from sqlalchemy import select

    from chameleon.core.infra.db import AsyncSessionLocal
    from chameleon.core.models import RetrievalEvaluation

    async with AsyncSessionLocal() as session:
        row = (
            await session.execute(
                select(RetrievalEvaluation).where(
                    RetrievalEvaluation.id == eval_id,
                    RetrievalEvaluation.kb_id == kb_id,
                )
            )
        ).scalar_one_or_none()
    if row is None:
        raise SystemExit(f"评估批次不存在: eval_id={eval_id} kb_id={kb_id}")
    return [
        EvalQuery(
            query=q["query"],
            expected=set(int(x) for x in q.get("expected_chunk_ids") or []),
        )
        for q in row.queries
    ]


async def _run_strategy(
    name: str, runner, queries: list[EvalQuery]
) -> StrategyStats:
    ranks: list[int | None] = []
    latencies: list[float] = []
    errors = 0
    for eq in queries:
        t0 = time.perf_counter()
        try:
            hit_ids = await runner(eq.query)
        except Exception as e:  # noqa: BLE001 —— 单 query 失败不拖垮整组
            errors += 1
            print(f"  [{name}] query 失败: {str(e)[:80]}", file=sys.stderr)
            ranks.append(None)
            continue
        latencies.append((time.perf_counter() - t0) * 1000.0)
        ranks.append(_first_hit_rank(hit_ids, eq.expected))
    return _aggregate(name, ranks, latencies, errors)


def _print_table(stats: list[StrategyStats], n_queries: int) -> None:
    print("\n" + "=" * 72)
    print(f"检索召回质量对比（{n_queries} queries）")
    print("=" * 72)
    header = f"{'strategy':<14}{'hit@1':>8}{'hit@3':>8}{'hit@5':>8}{'MRR':>8}{'P50ms':>9}{'err':>6}"
    print(header)
    print("-" * 72)
    for s in stats:
        print(
            f"{s.name:<14}"
            f"{s.hit_at[1]:>8.3f}{s.hit_at[3]:>8.3f}{s.hit_at[5]:>8.3f}"
            f"{s.mrr:>8.3f}{s.latency_p50_ms:>9.1f}{s.errors:>6}"
        )
    print("-" * 72)
    base = next((s for s in stats if s.name == "baseline"), None)
    if base and base.hit_at[5] > 0:
        for s in stats:
            if s.name == "baseline":
                continue
            delta = (s.hit_at[5] - base.hit_at[5]) / base.hit_at[5] * 100
            print(f"  {s.name} vs baseline hit@5: {delta:+.1f}%")


async def main() -> None:
    parser = argparse.ArgumentParser(description="检索召回质量基准")
    parser.add_argument("--kb", required=True, help="KB kb_key")
    parser.add_argument("--queries", type=Path, help="eval.json 路径")
    parser.add_argument("--eval-id", type=int, help="从已存 RetrievalEvaluation 取 query")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--multi-query-n", type=int, default=3)
    args = parser.parse_args()

    from chameleon.core.components.knowledge import get_kb_meta

    meta = await get_kb_meta(args.kb)
    if meta is None:
        raise SystemExit(f"KB 不存在: {args.kb}")

    if args.queries:
        queries = _load_queries_from_file(args.queries)
    elif args.eval_id:
        queries = await _load_queries_from_eval(meta.id, args.eval_id)
    else:
        raise SystemExit("必须提供 --queries 或 --eval-id")
    if not queries:
        raise SystemExit("query 集为空")

    complete_fn = _make_complete_fn()
    kb_id, model, top_k = meta.id, meta.embedding_model, args.top_k

    stats = [
        await _run_strategy(
            "baseline",
            lambda q: _run_baseline(
                kb_id=kb_id, embedding_model=model, query=q, top_k=top_k
            ),
            queries,
        ),
        await _run_strategy(
            "multi_query",
            lambda q: _run_multi_query(
                kb_id=kb_id,
                embedding_model=model,
                query=q,
                top_k=top_k,
                complete_fn=complete_fn,
                n=args.multi_query_n,
            ),
            queries,
        ),
        await _run_strategy(
            "hyde",
            lambda q: _run_hyde(
                kb_id=kb_id,
                embedding_model=model,
                query=q,
                top_k=top_k,
                complete_fn=complete_fn,
            ),
            queries,
        ),
    ]
    _print_table(stats, len(queries))


if __name__ == "__main__":
    asyncio.run(main())
