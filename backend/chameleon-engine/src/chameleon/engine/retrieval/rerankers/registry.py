"""Reranker 注册表 —— PR B3

build_reranker(config) → Reranker | None

红线：默认关。type 缺失 / "none" / "off" / 空 → 返 None（不重排）。
启用走 KB collection 配置（config dict 由调用方从 KB.meta / collection.config 取）。

config 形态：
    {
      "type": "bge" | "cohere" | "local_dedupe" | "llm_judge" | "none",
      "model": "bge-reranker-v2-m3",      # bge / cohere
      "base_url": "http://127.0.0.1:9997/v1/rerank",  # bge 自托管
      "api_key": "...",                   # cohere 必填 / bge 可选
      "top_n": 5,
      "dedupe_threshold": 0.85            # local_dedupe
    }

llm_judge 需注入 judge_fn（不可序列化），由 build_reranker 的 judge_fn 参数传入。
"""

from __future__ import annotations

from typing import Any

from chameleon.engine.retrieval.rerankers.base import JudgeFn, Reranker
from chameleon.engine.retrieval.rerankers.clients import (
    BgeReranker,
    CohereReranker,
    make_client_reranker,
)
from chameleon.engine.retrieval.rerankers.local import (
    make_dedupe_reranker,
    make_dedupe_then_judge_reranker,
    make_llm_judge_reranker,
)

_OFF = {"", "none", "off", "disabled", "passthrough"}


def build_reranker(
    config: dict[str, Any] | None,
    *,
    judge_fn: JudgeFn | None = None,
) -> Reranker | None:
    """按 config 造 reranker；默认 / 关闭态返 None

    Raises:
        ValueError: 启用了某类型但缺必填字段（base_url / api_key 等）
    """
    if not config:
        return None
    rtype = str(config.get("type") or "").strip().lower()
    if rtype in _OFF:
        return None

    top_n = config.get("top_n")
    top_n = int(top_n) if top_n else None

    if rtype == "bge":
        base_url = config.get("base_url")
        if not base_url:
            raise ValueError("reranker type=bge 需要 base_url")
        client = BgeReranker(
            base_url=base_url,
            model=config.get("model") or "bge-reranker-v2-m3",
            api_key=config.get("api_key"),
        )
        return make_client_reranker(client, keep_top_k=top_n)

    if rtype == "cohere":
        api_key = config.get("api_key")
        if not api_key:
            raise ValueError("reranker type=cohere 需要 api_key")
        client = CohereReranker(
            api_key=api_key,
            model=config.get("model") or "rerank-multilingual-v3.0",
            base_url=config.get("base_url") or "https://api.cohere.com/v2/rerank",
        )
        return make_client_reranker(client, keep_top_k=top_n)

    if rtype == "local_dedupe":
        threshold = float(config.get("dedupe_threshold") or 0.85)
        return make_dedupe_reranker(dedupe_threshold=threshold)

    if rtype == "llm_judge":
        if judge_fn is None:
            raise ValueError("reranker type=llm_judge 需要注入 judge_fn")
        threshold = config.get("dedupe_threshold")
        if threshold is not None:
            return make_dedupe_then_judge_reranker(
                judge_fn=judge_fn,
                dedupe_threshold=float(threshold),
                keep_top_k=top_n,
            )
        return make_llm_judge_reranker(judge_fn=judge_fn, keep_top_k=top_n)

    raise ValueError(f"未知 reranker type: {rtype!r}")
