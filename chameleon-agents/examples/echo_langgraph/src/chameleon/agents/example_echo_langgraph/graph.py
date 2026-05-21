"""echo agent —— 3 节点最简 LangGraph

route   → 决定要不要做 RAG（input 含 "doc:" 触发）
lookup  → 调 chameleon.core.knowledge.search_kb (如有 "doc:kb_key" 关键字)
respond → 调 EchoChatModel 按 chunk 流回 input
"""

from __future__ import annotations

import re
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import MessagesState

from chameleon.agents.example_echo_langgraph.echo_model import EchoChatModel

_DOC_PATTERN = re.compile(r"doc:([a-zA-Z0-9_-]+)")


class _State(MessagesState):
    """扩展 MessagesState 增加 citations / kb_key 字段"""

    citations: list[dict[str, Any]]
    kb_key: str | None


# ── 节点 ────────────────────────────────────────────────


async def _route_node(state: _State) -> dict[str, Any]:
    """检查最后一条 user message 是否含 doc:<kb_key> 标记"""
    last_user = _last_user_text(state["messages"])
    m = _DOC_PATTERN.search(last_user) if last_user else None
    return {"kb_key": m.group(1) if m else None, "citations": []}


async def _lookup_node(state: _State) -> dict[str, Any]:
    """命中 doc:<kb_key> 时调 search_kb 抓 citations"""
    kb_key = state.get("kb_key")
    if not kb_key:
        return {"citations": []}
    # 延迟 import 避免循环
    from chameleon.core.knowledge import search_kb

    query = _last_user_text(state["messages"]) or ""
    try:
        # min_score=-1.0：demo 优先展示命中，不卡阈值
        # 生产 agent 应根据 embedding 模型质量调整（如 0.3-0.5）
        hits = await search_kb(kb_key, query, top_k=3, min_score=-1.0)
    except Exception:
        return {"citations": []}
    citations = [
        {
            "source": f"chunk:{h.id}",
            "score": h.score,
            "snippet": h.content[:200],
        }
        for h in hits
    ]
    return {"citations": citations}


async def _respond_node(state: _State) -> dict[str, Any]:
    """用 EchoChatModel 按字符 stream 出 echo: <input>"""
    model = EchoChatModel()
    # ainvoke 内部会触发 on_chat_model_stream（因为我们 yield AIMessageChunk）
    result = await model.ainvoke(state["messages"])
    return {"messages": [result]}


# ── 路由函数 ────────────────────────────────────────────


def _should_lookup(state: _State) -> str:
    """conditional edge：有 kb_key 走 lookup，否则跳过到 respond"""
    return "lookup" if state.get("kb_key") else "respond"


# ── 图构建 ──────────────────────────────────────────────


def build_graph():
    """sync function（裁决 A4），返回 CompiledGraph

    LangGraphProvider 启动时调用一次，缓存编译产物。
    """
    sg = StateGraph(_State)
    sg.add_node("route", _route_node)
    sg.add_node("lookup", _lookup_node)
    sg.add_node("respond", _respond_node)

    sg.add_edge(START, "route")
    sg.add_conditional_edges(
        "route",
        _should_lookup,
        {
            "lookup": "lookup",
            "respond": "respond",
        },
    )
    sg.add_edge("lookup", "respond")
    sg.add_edge("respond", END)

    return sg.compile()


# ── helpers ─────────────────────────────────────────────


def _last_user_text(messages: list[BaseMessage] | list[dict]) -> str | None:
    if not messages:
        return None
    for m in reversed(messages):
        if isinstance(m, HumanMessage):
            content = m.content
        elif isinstance(m, AIMessage):
            continue
        elif isinstance(m, dict):
            if m.get("role") != "user":
                continue
            content = m.get("content", "")
        else:
            continue
        if isinstance(content, list):
            parts = [p.get("text", "") for p in content if isinstance(p, dict)]
            return "".join(parts)
        if isinstance(content, str):
            return content
        return None
    return None
