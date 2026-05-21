"""Chameleon AI 工具箱（吸收 sage components 习惯）

统一的"AI 基础能力门面"——agent 业务代码统一从这里 import：

    from chameleon.core.components import llm, embedding, vector, cache, search_kb

各子模块：
- llms/        —— LLM 客户端（BaseLLM + 多厂商）
- embeddings/  —— embedding 客户端
- vector/      —— 向量存储（VectorStore + pgvector）
- cache/       —— diskcache 单例
- knowledge    —— in-process KB API（search_kb / get_kb_meta）
- inventory    —— ★ 全局具名访问点（仿 sage 的 components/inventory.py）
"""

from chameleon.core.components.inventory import (
    cache,
    embedding,
    llm,
    llm_by_name,
    search_kb,
    vector,
)

__all__ = [
    "cache",
    "embedding",
    "llm",
    "llm_by_name",
    "search_kb",
    "vector",
]
