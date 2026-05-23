"""ChunkPayload —— chunker 输出的统一形态

ingest pipeline 拿到 list[ChunkPayload] 后映射到 ORM Chunk：
- content       → Chunk.content
- index_name    → Chunk.index_name
- qa_question   → Chunk.qa_question
- api_endpoint  → Chunk.api_endpoint
- meta          → Chunk.meta（heading_path / api_method / 其他）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ChunkPayload:
    """单个 chunk 的待入库 payload"""

    content: str
    index_name: str = "chunk"
    qa_question: str | None = None
    api_endpoint: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)
