"""`@agent` —— 把作者声明捕获成 AgentManifest 并登记到模块级 DECLARED。

两种入口：
- 函数式：`@agent(...)` 装饰 `async def handle(ctx) -> str | AsyncIterator[str]`
- 类式：`@agent(...)` 装饰 BaseAgent 子类（高级 / 有状态用法）

注册期由发现机制读 `declared_agents()` 建 registry（后续 phase）。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from chameleon.agentkit._spec import AgentManifest, ModelSlot, Opt

# 模块级声明登记表：import agent 模块即登记，发现机制注册期读取
_DECLARED: dict[str, AgentManifest] = {}

T = TypeVar("T")


def agent(
    *,
    key: str,
    name: str,
    description: str | None = None,
    models: list[ModelSlot] | None = None,
    kb: bool = False,
    config: list[Opt] | None = None,
    tags: list[str] | None = None,
) -> Callable[[T], T]:
    """声明一个本地智能体。

    挂 `__agent_manifest__` 到目标对象，并登记到 `_DECLARED`。
    `key` 全局唯一，重复声明直接报错。
    """

    def deco(target: T) -> T:
        if key in _DECLARED:
            raise ValueError(f"重复声明的 agent key: {key}")
        manifest = AgentManifest(
            key=key,
            name=name,
            description=description,
            models=list(models or []),
            kb=kb,
            config=list(config or []),
            tags=list(tags or []),
            handler=target,
            is_class=isinstance(target, type),
        )
        _DECLARED[key] = manifest
        target.__agent_manifest__ = manifest  # type: ignore[attr-defined]
        return target

    return deco


def declared_agents() -> dict[str, AgentManifest]:
    """注册期读取所有 `@agent` 声明（registry / 发现机制用）。"""
    return dict(_DECLARED)
