"""A2A 调用桥（IoC）—— 让不依赖 engine 的层（agentkit runner）也能发起子智能体调用。

`engine.agent.a2a.call_agent` 是真正实现，但 providers-local（agentkit runner 所在）
不依赖 engine。仿 core.base.bridge_registry / observe.sink 的反转：app 启动时由 engine
侧注入 caller，runner 经 `get_a2a_caller()` 委托调用，不直接 import engine。

caller 契约（避免在本层 import engine 类型，用纯参数 + dict 返回）：

    async def caller(*, source: str, target: str, input, trace_id: str,
                     budget_remaining: int, depth: int) -> dict
    # 返回 {"answer": str, "tokens": int, "sub_observation_id": str | None}
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

A2ACaller = Callable[..., Awaitable[dict[str, Any]]]

_CALLER: A2ACaller | None = None


def set_a2a_caller(fn: A2ACaller) -> None:
    global _CALLER
    _CALLER = fn


def get_a2a_caller() -> A2ACaller | None:
    return _CALLER
