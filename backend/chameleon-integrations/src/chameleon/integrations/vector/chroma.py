"""Chroma 占位实现（v1 不启用，留作后续切换样板）"""

from chameleon.core.vector.base import ChunkHit, ChunkPayload, VectorStore


class ChromaStore(VectorStore):
    backend = "chroma"

    async def upsert(self, *, kb_id, doc_id, chunks: list[ChunkPayload]) -> None:
        raise NotImplementedError(
            "ChromaStore: 占位实现。需要时按 PgVectorStore 接口照写即可。"
        )

    async def search(
        self, *, kb_id, query_vec, top_k=5, min_score=0.0
    ) -> list[ChunkHit]:
        raise NotImplementedError("ChromaStore: 占位实现")

    async def delete(self, *, kb_id, doc_id=None) -> int:
        raise NotImplementedError("ChromaStore: 占位实现")

    async def healthcheck(self) -> bool:
        return False
