"""向量存储实现层：pgvector / chroma + get_store 工厂。

协议（VectorStore / ChunkHit / ChunkPayload）在 chameleon.core.vector.base。
"""

from chameleon.integrations.vector.factory import get_store
from chameleon.integrations.vector.pgvector import PgVectorStore

__all__ = ["PgVectorStore", "get_store"]
