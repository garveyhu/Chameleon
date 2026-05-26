"""VectorStore 协议 + 载体类型"""

from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel, Field


class ChunkPayload(BaseModel):
    """upsert 用：写入一个 chunk 的全部字段（id 可空，store 自分配）"""

    content: str
    embedding: list[float]
    seq: int = 0
    token_count: int | None = None
    meta: dict[str, Any] | None = None
    #: parent-child 分层：child 所属 parent 大块全文（命中时作上下文返回）
    parent_content: str | None = None


class ChunkHit(BaseModel):
    """search 用：命中一个 chunk"""

    id: int
    doc_id: int
    seq: int
    content: str
    score: float = Field(..., description="相似度，越大越相近（cosine: 1 - distance）")
    meta: dict[str, Any] | None = None


class VectorStore(Protocol):
    """统一向量存储接口"""

    backend: str  # "pgvector" / "chroma" / ...

    async def upsert(
        self, *, kb_id: int, doc_id: int, chunks: list[ChunkPayload]
    ) -> None:
        """批量写入 chunks。重复 seq 视为更新（按 doc_id+seq 唯一）"""
        ...

    async def search(
        self,
        *,
        kb_id: int,
        query_vec: list[float],
        top_k: int = 5,
        min_score: float = 0.0,
    ) -> list[ChunkHit]:
        """语义检索"""
        ...

    async def delete(self, *, kb_id: int, doc_id: int | None = None) -> int:
        """删除指定 kb 或 kb+doc 的全部 chunks，返删除条数"""
        ...

    async def healthcheck(self) -> bool: ...
