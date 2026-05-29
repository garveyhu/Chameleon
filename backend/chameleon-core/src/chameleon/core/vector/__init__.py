"""向量存储抽象（协议层）

具体实现（pgvector / chroma / get_store 工厂）已移到 chameleon.integrations.vector。
core 只留 VectorStore 协议 + ChunkHit / ChunkPayload 数据结构。
"""

from chameleon.core.vector.base import ChunkHit, ChunkPayload, VectorStore

__all__ = ["ChunkHit", "ChunkPayload", "VectorStore"]
