"""EmbeddingClient 协议（协议层）

具体实现（OpenAI 兼容 client / 工厂 / 图片 embedder）已移到
chameleon.integrations.embedding。core 只留 EmbeddingClient 协议。
"""

from chameleon.core.embedding.base import EmbeddingClient

__all__ = ["EmbeddingClient"]
