"""example_echo_native: 纯 Python async generator 范式样板

★ 演示要点：本地 agent **完全不绑 LangGraph 或 LangChain**。
agent 继承 BaseAgent，实现 `astream(ctx)` async generator，自由 yield。

适合场景：
- agent 逻辑简单到不需要 LangGraph 多节点编排
- 用了非 LangChain 生态的 LLM client（如 Anthropic 原生 SDK、自研客户端）
- 想要极致灵活控制流式输出（手动 yield 任意 event 类型）
"""

# 必须 import schemas 触发 @register 装饰器副作用
from chameleon.agents.example_echo_native import schemas as _schemas  # noqa: F401
from chameleon.agents.example_echo_native.agent import EchoNativeAgent
from chameleon.agents.example_echo_native.schemas import EchoAgentInput

__all__ = ["EchoNativeAgent", "EchoAgentInput"]
__version__ = "0.1.0"
