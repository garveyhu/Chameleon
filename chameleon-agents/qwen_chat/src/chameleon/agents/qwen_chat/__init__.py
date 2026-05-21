"""qwen_chat: 真实通用聊天 agent

调真实 Qwen（或 model.json 配置的任何 LLM），走 BaseAgent + build_runnable
最简范式：一个 prompt | llm 链。

调用方式：
    POST /v1/agents/qwen-chat/invoke
    Body: {"input": "你好", "stream": true}
"""

from chameleon.agents.qwen_chat.agent import QwenChatAgent

__all__ = ["QwenChatAgent"]
__version__ = "0.1.0"
