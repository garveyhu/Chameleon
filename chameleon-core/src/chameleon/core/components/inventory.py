"""components/inventory.py —— 全局组件具名访问点（仿 sage components/inventory）

★ 这里和 `chameleon.core.config.inventory` 区分：
  - core/config/inventory: 配置项的具名 getter（log_level / database_url / case_llm 等）
  - core/components/inventory: 组件实例的具名 getter（llm / embedding / vector / cache）

业务代码统一从这里 import：

    from chameleon.core.components import llm, embedding, vector, cache, search_kb

    chat_model = llm()                 # LLM 客户端
    embedder = embedding()              # embedding 客户端
    store = vector()                    # VectorStore
    c = cache()                         # CacheManager
    hits = await search_kb("my-kb", "query")
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any

# ── 请求级单例缓存（仿 sage 的 _request_llm_instance_ctx 模式） ────


_request_llm_instance_ctx: ContextVar[Any] = ContextVar(
    "_chameleon_request_llm_ctx", default=None
)


def reset_request_singletons() -> None:
    """在请求结束时（HTTP middleware finally 钩子）调用，重置请求级实例

    v1 暂未在 middleware 强制接入；调用方按需用。
    """
    _request_llm_instance_ctx.set(None)


# ── LLM ─────────────────────────────────────────────────


def llm(name: str | None = None):
    """获取 LLM 实例（请求级单例 + 模块级缓存）

    name=None → 用全局默认（model.json cases.llm）
    """
    # 请求级缓存
    cached = _request_llm_instance_ctx.get()
    if cached is not None and name is None:
        return cached

    from chameleon.core.components.llms.factory import LLMFactory

    instance = LLMFactory.create(name)
    if name is None:
        _request_llm_instance_ctx.set(instance)
    return instance


def llm_by_name(name: str):
    """按模型名取 LLM（与 sage 同名）"""
    from chameleon.core.components.llms.factory import LLMFactory

    return LLMFactory.create(name)


# ── Embedding ───────────────────────────────────────────


def embedding(name: str | None = None):
    """获取 embedding 客户端"""
    from chameleon.core.embedding.factory import get_embedding_client

    return get_embedding_client(name)


# ── Vector Store ────────────────────────────────────────


def vector():
    """获取 VectorStore 实例（v1 默认 PgVectorStore）"""
    from chameleon.core.vector.factory import get_store

    return get_store()


# ── Cache ───────────────────────────────────────────────


def cache():
    """获取 CacheManager 实例（diskcache 单例）"""
    from chameleon.core.components.cache.manager import CacheManager

    return CacheManager()


# ── Knowledge Base 检索（in-process） ──────────────────


async def search_kb(
    kb_key: str,
    query: str,
    *,
    top_k: int | None = None,
    min_score: float = 0.0,
):
    """语义检索 KB（薄包装 chameleon.core.knowledge.search_kb）"""
    from chameleon.core.knowledge import search_kb as _search_kb

    return await _search_kb(kb_key, query, top_k=top_k, min_score=min_score)
