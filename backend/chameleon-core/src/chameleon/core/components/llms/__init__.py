"""LLM 客户端工厂（吸收 sage components/llms 习惯）

设计：
- BaseLLM 继承 langchain_openai.ChatOpenAI（与 sage 一致）
- 所有 OpenAI 兼容厂商共用 BaseLLM；厂商类（ChatQwen / ChatDeepSeek 等）
  只是显式 alias，便于 isinstance 判断 + 文档可读性
- 与 sage 的差异：sage 从 DB（ai_models 表）读配置；chameleon 从 model.json 读

用法：

    from chameleon.core.components import llm

    chat = llm()                      # 用全局默认（model.json cases.llm）
    chat = llm("qwen-plus")            # 按名指定

    # 直接构造（少见，用于绕过 factory 的场景）
    from chameleon.core.components.llms import BaseLLM, ChatQwen
    chat = BaseLLM(model="...", api_key="...", api_base="...")
"""

from chameleon.core.components.llms.base import (
    BaseLLM,
    ChatDeepSeek,
    ChatOpenAI,
    ChatQwen,
)
from chameleon.core.components.llms.factory import LLMFactory, llm, llm_by_name

__all__ = [
    "BaseLLM",
    "ChatDeepSeek",
    "ChatOpenAI",
    "ChatQwen",
    "LLMFactory",
    "llm",
    "llm_by_name",
]
