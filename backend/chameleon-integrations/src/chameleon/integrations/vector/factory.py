"""VectorStore 工厂

v1 默认 pgvector；扩展时改这里 + 加 backend 实现。
"""

from __future__ import annotations

from chameleon.core.config import inventory
from chameleon.core.vector.base import VectorStore
from chameleon.integrations.vector.chroma import ChromaStore
from chameleon.integrations.vector.pgvector import PgVectorStore

_STORE: VectorStore | None = None
_OVERRIDE: VectorStore | None = None  # 测试用


def set_for_test(store: VectorStore | None) -> None:
    global _OVERRIDE
    _OVERRIDE = store


def get_store() -> VectorStore:
    if _OVERRIDE is not None:
        return _OVERRIDE
    global _STORE
    if _STORE is not None:
        return _STORE

    backend = _resolve_backend()
    if backend == "pgvector":
        _STORE = PgVectorStore()
    elif backend == "chroma":
        _STORE = ChromaStore()
    else:
        raise ValueError(f"unknown vector backend: {backend}")
    return _STORE


def _resolve_backend() -> str:
    # 留个 config 出口；默认 pgvector
    return (
        getattr(inventory, "vector_backend", lambda: None)()
        if hasattr(inventory, "vector_backend")
        else None
    ) or "pgvector"
