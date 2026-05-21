"""chameleon-agent-echo-runnable: LangChain Runnable (LCEL) 范式样板

★ 演示要点：用 LangChain LCEL（`prompt | llm | parser`）写 agent，
通过 BaseAgent.from_runnable() 桥自动产生 StreamEvent。

适合场景：
- 简单的 LLM 调用链（一次 prompt → 一次 LLM → 一次解析）
- 已熟悉 LangChain LCEL 风格
- 不需要 LangGraph 多节点状态机的复杂度
"""

from chameleon.agents.echo_runnable.agent import EchoRunnableAgent

__all__ = ["EchoRunnableAgent"]
__version__ = "0.1.0"
