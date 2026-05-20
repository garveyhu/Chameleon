"""chameleon-agent-echo: echo 智能体

范式样板：
- 演示 step（route/lookup/respond 节点完成） + delta（按 chunk 流） + citation（RAG）三类 event
- input 含 "doc:<kb_key>" 时自动 RAG 检索该知识库
- 用 EchoChatModel 作为"假 LLM"避免依赖真实 API key（仅用于演示）

key = "echo"  → registry 自动扫到
"""

from chameleon.agents.echo.graph import build_graph

AGENT_META = {
    "key": "echo",
    "description": "回声智能体：演示 step/delta/citation 三类事件；input 含 doc:<kb_key> 触发 RAG",
    "version": "0.1",
    "tags": ["builtin", "demo"],
}

__all__ = ["AGENT_META", "build_graph"]
__version__ = "0.1.0"
