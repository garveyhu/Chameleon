"""embeddings 子模块 —— 仿 sage components/embeddings 命名

v1 实现在 chameleon.core.embedding（单数）；这里 re-export + 加新厂商类时
逐步迁移。仿 sage 同样支持 OpenAI / DashScope(Qwen) / Local，但 v1 仅默认
OpenAI 兼容协议（DashScope/Local 占位）。
"""

from chameleon.core.embedding.base import EmbeddingClient
from chameleon.core.embedding.factory import (
    get_embedding_client,
    set_for_test,
)
from chameleon.core.embedding.openai_compat import OpenAICompatEmbedding

# sage 风格命名别名（让 sage 用户看着顺）
OpenAIEmbeddings = OpenAICompatEmbedding  # OpenAI 协议兼容（含 DeepSeek/Qwen 兼容模式）
DashScopeEmbeddings = OpenAICompatEmbedding  # 阿里云 DashScope 也走 OpenAI 兼容

__all__ = [
    "DashScopeEmbeddings",
    "EmbeddingClient",
    "OpenAICompatEmbedding",
    "OpenAIEmbeddings",
    "get_embedding_client",
    "set_for_test",
]
