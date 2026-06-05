"""rerank 模型客户端 + 工厂（integrations 层，与 embedding 对等）。

rerank 作为「模型」收口到这里：DB 驱动 + 网关感知的工厂 `get_reranker(name)`，
业务/engine 经此取 rerank 客户端。客户端返回中性 `RerankResult`（不依赖
engine 的 RerankScore，遵守 engine→integrations 单向分层）。
"""

from chameleon.integrations.rerank.factory import (
    get_reranker,
    invalidate_rerank,
    reload_rerank_cache,
    set_for_test,
)
from chameleon.integrations.rerank.openai_compat import (
    OpenAICompatReranker,
    RerankResult,
)

__all__ = [
    "OpenAICompatReranker",
    "RerankResult",
    "get_reranker",
    "invalidate_rerank",
    "reload_rerank_cache",
    "set_for_test",
]
