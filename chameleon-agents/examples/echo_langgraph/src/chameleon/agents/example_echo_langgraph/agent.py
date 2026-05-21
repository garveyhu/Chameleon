"""EchoLangGraphAgent —— LangGraph 范式样板（BaseAgent 子类）"""

from __future__ import annotations

from chameleon.agents.example_echo_langgraph.graph import build_graph as _build_graph
from chameleon.core.base import AgentMetadata, BaseAgent


class EchoLangGraphAgent(BaseAgent):
    """演示 LangGraph CompiledGraph 范式

    实现 build_graph() classmethod 后，BaseAgent 默认 astream 会自动用
    from_langgraph_graph() 桥翻译事件流，无需写 stream 代码。
    """

    @classmethod
    def get_metadata(cls) -> AgentMetadata:
        return AgentMetadata(
            id="example-echo-langgraph",
            name="Echo (LangGraph)",
            description=(
                "LangGraph CompiledGraph 范式样板：route/lookup/respond 三节点；"
                "input 含 doc:<kb_key> 触发 RAG。"
            ),
            version="0.1",
            tags=["builtin", "example", "langgraph"],
        )

    @classmethod
    def build_graph(cls):
        return _build_graph()
