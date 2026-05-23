"""generic collection chunker —— 沿用现有 chunker.split"""

from __future__ import annotations

from typing import Any

from chameleon.api.knowledge.chunker import split
from chameleon.api.knowledge.chunkers.base import ChunkPayload


def chunk_generic(
    text: str, config: dict[str, Any] | None = None
) -> list[ChunkPayload]:
    """通用文档 chunker：跑现有 strategy → ChunkPayload 列表"""
    strategies = (config or {}).get("strategy") or config
    parts = split(text, strategies)
    return [ChunkPayload(content=p, index_name="chunk") for p in parts]
