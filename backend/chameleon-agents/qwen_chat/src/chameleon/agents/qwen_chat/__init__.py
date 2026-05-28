"""qwen_chat: 通用聊天 agent（agentkit @agent 范式样板）。

只写业务逻辑，模型从 ctx 隐式拿（页面"关联模型"可切换）。

调用方式：
    POST /v1/invoke（body.agent_key=qwen-chat 或用绑定的 app-scoped key）
    Body: {"input": "你好", "stream": true}
"""

from chameleon.agents.qwen_chat.agent import handle

__all__ = ["handle"]
__version__ = "0.2.0"
