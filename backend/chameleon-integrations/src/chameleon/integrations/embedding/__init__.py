"""embedding 实现层：OpenAI 兼容 client 工厂 + 图片 embedder。

协议（EmbeddingClient）在 chameleon.core.embedding.base。
"""

from chameleon.integrations.embedding.factory import get_embedding_client, set_for_test
from chameleon.integrations.embedding.image import (
    CaptionFn,
    ImageEmbedder,
    ImageEmbedResult,
)
from chameleon.integrations.embedding.openai_compat import OpenAICompatEmbedding

__all__ = [
    "CaptionFn",
    "ImageEmbedResult",
    "ImageEmbedder",
    "OpenAICompatEmbedding",
    "get_embedding_client",
    "set_for_test",
]
