"""Agent 范式桥的 DI 注册点。

BaseAgent.astream 在 agent 定义 build_graph()/build_runnable() 时，委托这里注册的
桥把 LangGraph CompiledGraph / LangChain Runnable 转成 StreamEvent 流。

具体桥实现在 chameleon.integrations.bridges，由应用启动（及测试 conftest）调
`wire_agent_bridges()` 注入——core 因此不反向 import integrations，保持纯协议。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Protocol


class BridgeFn(Protocol):
    """ctx + 目标对象（graph / runnable）→ StreamEvent 异步流。"""

    def __call__(self, ctx: Any, target: Any, **kwargs: Any) -> AsyncIterator[Any]: ...


_langgraph_bridge: BridgeFn | None = None
_runnable_bridge: BridgeFn | None = None


def set_langgraph_bridge(fn: BridgeFn) -> None:
    global _langgraph_bridge
    _langgraph_bridge = fn


def set_runnable_bridge(fn: BridgeFn) -> None:
    global _runnable_bridge
    _runnable_bridge = fn


def get_langgraph_bridge() -> BridgeFn:
    if _langgraph_bridge is None:
        raise RuntimeError(
            "LangGraph 桥未注册——应用启动应调 "
            "chameleon.integrations.bridges.wire_agent_bridges()"
        )
    return _langgraph_bridge


def get_runnable_bridge() -> BridgeFn:
    if _runnable_bridge is None:
        raise RuntimeError(
            "LangChain Runnable 桥未注册——应用启动应调 "
            "chameleon.integrations.bridges.wire_agent_bridges()"
        )
    return _runnable_bridge
