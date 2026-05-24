"""KB collection 类型专用 chunker —— P20.3 PR #52

每种 collection_type 一套 chunker：
- generic  —— 沿用 chunker.py:split（fixed / paragraph / sentence / regex / token）
- faq      —— 解析 Q/A markdown，每对一 chunk + 填 qa_question
- wiki     —— 按 heading 切，meta 含 heading_path
- api      —— 解析 OpenAPI YAML/JSON，每 endpoint 一 chunk + 填 api_endpoint

dispatch：`get_chunker(collection_type)` → callable(text, config) → list[ChunkPayload]
"""

from chameleon.api.knowledge.chunkers.api import chunk_api
from chameleon.api.knowledge.chunkers.base import ChunkPayload
from chameleon.api.knowledge.chunkers.faq import chunk_faq
from chameleon.api.knowledge.chunkers.generic import chunk_generic
from chameleon.api.knowledge.chunkers.wiki import chunk_wiki

_REGISTRY = {
    "generic": chunk_generic,
    "faq": chunk_faq,
    "wiki": chunk_wiki,
    "api": chunk_api,
}


def get_chunker(collection_type: str):
    """按 collection_type 返 chunker 函数；未知类型 raise ValueError"""
    fn = _REGISTRY.get(collection_type)
    if fn is None:
        raise ValueError(
            f"未支持的 collection_type={collection_type!r}；"
            f"可选: {sorted(_REGISTRY.keys())}"
        )
    return fn


__all__ = [
    "ChunkPayload",
    "chunk_api",
    "chunk_faq",
    "chunk_generic",
    "chunk_wiki",
    "get_chunker",
]
