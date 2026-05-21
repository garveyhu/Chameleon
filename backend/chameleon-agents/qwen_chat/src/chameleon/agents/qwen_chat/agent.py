"""QwenChatAgent —— 真实 LLM 通用聊天 agent

设计意图：
- 不写自定义 graph、不写节点；直接 prompt | llm
- 走 chameleon.core.components.llm() 拿全局默认 LLM
  （model.json cases.llm 字段决定，可在不重启代码的前提下切换厂商）
- 演示生产级 agent 的最小完整范式
"""

from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate

from chameleon.core.base import AgentMetadata, BaseAgent
from chameleon.core.components import llm

SYSTEM_PROMPT = """你是 Chameleon 的通用聊天助手。
要点：回答简洁、自然、有用；尽量用中文；适当使用 Markdown 格式。"""


class QwenChatAgent(BaseAgent):
    @classmethod
    def get_metadata(cls) -> AgentMetadata:
        return AgentMetadata(
            id="qwen-chat",
            name="通用聊天",
            description="直接对接 model.json 配置的默认 LLM（默认 qwen-plus）",
            version="0.1",
            tags=["builtin", "chat", "qwen"],
        )

    @classmethod
    def build_runnable(cls):
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", SYSTEM_PROMPT),
                ("placeholder", "{history}"),
                ("user", "{input}"),
            ]
        )
        return prompt | llm()
