"""LLM 客户端实现层：BaseLLM（langchain_openai 封装）+ 厂商 alias + 工厂。

无 LLM 协议留在 core —— core 侧消费方（components/inventory）只在函数体内
inline 取实例并按 langchain BaseChatModel 鸭子接口使用，不依赖自定义类型。
"""

from chameleon.integrations.llms.base import (
    BaseLLM,
    ChatDeepSeek,
    ChatOpenAI,
    ChatQwen,
)
from chameleon.integrations.llms.factory import (
    LLMFactory,
    invalidate_llm,
    llm,
    llm_by_name,
    reload_llm_cache,
    resolve_llm,
    set_for_test,
)

__all__ = [
    "BaseLLM",
    "ChatDeepSeek",
    "ChatOpenAI",
    "ChatQwen",
    "LLMFactory",
    "invalidate_llm",
    "llm",
    "llm_by_name",
    "reload_llm_cache",
    "resolve_llm",
    "set_for_test",
]
