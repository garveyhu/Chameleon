"""embedding client 工厂

v1 仅支持 OpenAI 兼容协议（裁决 A9）：OpenAI / DeepSeek / Qwen 兼容模式 / vLLM 同走。
"""

from chameleon.core.embedding.base import EmbeddingClient
from chameleon.core.embedding.factory import get_embedding_client, set_for_test
from chameleon.core.embedding.image import (
    CaptionFn,
    ImageEmbedder,
    ImageEmbedResult,
)

__all__ = [
    "CaptionFn",
    "EmbeddingClient",
    "ImageEmbedResult",
    "ImageEmbedder",
    "get_embedding_client",
    "set_for_test",
]
