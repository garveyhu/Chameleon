"""retrievers/ —— LangChain BaseRetriever 实现（KB 向量检索）。

通过 LangChain 回调总线自动出 retriever trace 节点（方案 A），与 LLM 同套机制。
"""

from chameleon.integrations.retrievers.kb_retriever import KbRetriever, get_kb_retriever

__all__ = ["KbRetriever", "get_kb_retriever"]
