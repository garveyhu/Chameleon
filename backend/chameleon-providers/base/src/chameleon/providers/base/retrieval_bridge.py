"""高级检索桥（IoC）—— 让 agentkit ctx.kb.search 用上 engine 的 hybrid+rerank+扩展。

`engine/retrieval/pipeline.retrieve` 是完整检索管道（hybrid/RRF/multi-query/HyDE/
rerank/parent-child），但 agentkit runner（providers-local）不依赖 engine。仿
a2a_bridge / observe.sink 的反转：app 启动由 engine 侧注入 retrieve fn，runner 经
`get_retrieve_fn()` 委托；桥未注入则回退基础向量 `search_kb`。

fn 契约（避免在本层 import engine 类型，纯参数 + dict 返回）：

    async def fn(kb_key: str, query: str, *, top_k, min_score, mode, rerank, expand, hyde)
        -> list[dict]   # [{content, score, doc_id, seq, meta}]
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

RetrieveFn = Callable[..., Awaitable[list[dict[str, Any]]]]

_FN: RetrieveFn | None = None


def set_retrieve_fn(fn: RetrieveFn) -> None:
    global _FN
    _FN = fn


def get_retrieve_fn() -> RetrieveFn | None:
    return _FN
