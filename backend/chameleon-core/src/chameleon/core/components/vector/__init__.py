"""vector 子模块 —— 仿 sage components/vector 命名

re-export 自 chameleon.core.vector。
"""

from chameleon.core.vector import (
    ChunkHit,
    ChunkPayload,
    VectorStore,
    get_store,
)
from chameleon.core.vector.pgvector import PgVectorStore

__all__ = [
    "ChunkHit",
    "ChunkPayload",
    "PgVectorStore",
    "VectorStore",
    "get_store",
]
