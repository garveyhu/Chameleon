"""EmbeddingClient 协议"""

from __future__ import annotations

from typing import Protocol


class EmbeddingClient(Protocol):
    """统一 embedding 接口"""

    model: str
    dim: int

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """批量向量化。返回长度 == 输入长度，每条向量长度 == dim。"""
        ...
