"""example_echo_langgraph: LangGraph CompiledGraph 范式样板（BaseAgent 子类）

演示 step（节点完成） + delta（按 chunk 流） + citation（RAG）三类 event。
input 含 "doc:<kb_key>" 时自动 RAG 检索该知识库。

BaseAgent + build_graph classmethod 范式：默认 astream 走 from_langgraph_graph 桥，
无需自己写 stream 翻译。
"""

from chameleon.agents.example_echo_langgraph.agent import EchoLangGraphAgent

__all__ = ["EchoLangGraphAgent"]
__version__ = "0.1.0"
