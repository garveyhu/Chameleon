"""语义记忆向量桥（IoC）—— 让 agentkit ctx.memory.search/set 用上 engine 的 embed+hybrid。

memory 的 embedding/hybrid 召回实现在 engine（复用 retrieval pipeline 积木：
get_embedding_client + HybridPipeline + build_reranker），但 agentkit runner
（providers-local）不依赖 engine。仿 [[retrieval_bridge]]：app 启动由 engine 侧注入
index/search fn，runner 经 get_*_fn 委托；桥未注入则 memory 仅 KV（无语义召回）。

fn 契约（不在本层 import engine 类型，纯参数 + dict 返回）：

    async def index_fn(agent_key, scope_ref, mkey, text) -> None
        # embed + upsert 向量行；text="" / None → 删除该行（值被清空时同步）

    async def search_fn(agent_key, scope_ref, query, *, top_k, min_score) -> list[dict]
        # [{key, text, score}]，按 (agent_key, scope_ref) 隔离的 hybrid 召回结果
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

IndexFn = Callable[..., Awaitable[None]]
SearchFn = Callable[..., Awaitable[list[dict[str, Any]]]]

_INDEX_FN: IndexFn | None = None
_SEARCH_FN: SearchFn | None = None


def set_memory_index_fn(fn: IndexFn) -> None:
    global _INDEX_FN
    _INDEX_FN = fn


def get_memory_index_fn() -> IndexFn | None:
    return _INDEX_FN


def set_memory_search_fn(fn: SearchFn) -> None:
    global _SEARCH_FN
    _SEARCH_FN = fn


def get_memory_search_fn() -> SearchFn | None:
    return _SEARCH_FN
