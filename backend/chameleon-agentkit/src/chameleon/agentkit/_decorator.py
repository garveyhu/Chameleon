"""`@agent` —— 把作者声明捕获成 AgentManifest 并登记到模块级 DECLARED。

两种入口：
- 函数式：`@agent(...)` 装饰 `async def handle(ctx) -> str | AsyncIterator[str]`
- 类式：`@agent(...)` 装饰 BaseAgent 子类（高级 / 有状态用法）

注册期由发现机制读 `declared_agents()` 建 registry（后续 phase）。
"""

from __future__ import annotations

import inspect
import typing
from collections.abc import Callable
from typing import Any, TypeVar

from chameleon.agentkit._spec import (
    AgentManifest,
    McpServerConfig,
    ModelSlot,
    Opt,
    ToolSpec,
)

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
    tools: list[str] | None = None,
    sandboxed: bool = False,
    trust_tier: str = "internal",
    mcp_servers: list[McpServerConfig] | None = None,
    call_agents: list[str] | None = None,
) -> Callable[[T], T]:
    """声明一个本地智能体。

    挂 `__agent_manifest__` 到目标对象，并登记到 `_DECLARED`。
    `key` 全局唯一，重复声明直接报错。

    Args:
        tools: 平台 registry 工具点名（tool_key 列表）；web「关联工具」据此列出
            可启停集。代码自定义工具用 `@tool` 声明、运行时传给 `ctx.run_with_tools`。
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
            tools=list(tools or []),
            sandboxed=sandboxed,
            trust_tier=trust_tier,
            mcp_servers=list(mcp_servers or []),
            call_agents=list(call_agents or []),
            handler=target,
            is_class=isinstance(target, type),
        )
        _DECLARED[key] = manifest
        target.__agent_manifest__ = manifest  # type: ignore[attr-defined]
        # 类式 @agent：未自定义 get_metadata 则从 manifest 自动合成（单一真相源，
        # 消除 @agent 与 get_metadata 重复声明 + 漂移）。作者要差异化仍可显式 override。
        if isinstance(target, type) and "get_metadata" not in target.__dict__:
            from chameleon.core.base import AgentMetadata

            def _gen(cls: type, _m: AgentManifest = manifest) -> AgentMetadata:
                return AgentMetadata(
                    id=_m.key,
                    name=_m.name,
                    description=_m.description or "",
                    tags=list(_m.tags),
                )

            target.get_metadata = classmethod(_gen)  # type: ignore[attr-defined]
            # 合成的是 BaseAgent 的抽象方法 → 同步从 __abstractmethods__ 移除，否则
            # 实例化仍报「抽象类不可实例化」。
            abs = getattr(target, "__abstractmethods__", frozenset())
            if "get_metadata" in abs:
                target.__abstractmethods__ = frozenset(abs - {"get_metadata"})  # type: ignore[attr-defined]
        return target

    return deco


def declared_agents() -> dict[str, AgentManifest]:
    """注册期读取所有 `@agent` 声明（registry / 发现机制用）。"""
    return dict(_DECLARED)


# —— 本地工具声明（@tool）————————————————————————————————

_PY_TO_JSON = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    list: "array",
    dict: "object",
}


def tool(
    *,
    name: str | None = None,
    description: str = "",
) -> Callable[[T], T]:
    """把作者的 async 函数声明成一个本地工具。

    用法::

        @tool(name="get_weather", description="查询城市当前天气")
        async def get_weather(city: str) -> dict:
            ...

    从函数签名自动推断 `parameters_schema`（标量类型 → JSON Schema；无默认值 =
    required）。挂 `__tool_spec__` 到函数并原样返回——函数仍可正常直接调用。
    复杂入参（pydantic / 嵌套）超出 MVP 推断范围时，作者可手动覆盖
    `fn.__tool_spec__.parameters_schema`。
    """

    def deco(fn: T) -> T:
        if not inspect.iscoroutinefunction(fn):
            raise TypeError(f"@tool 只能装饰 async 函数: {getattr(fn, '__name__', fn)!r}")
        tool_name = name or fn.__name__
        schema = _infer_parameters_schema(fn)
        fn.__tool_spec__ = ToolSpec(  # type: ignore[attr-defined]
            name=tool_name,
            description=description or (inspect.getdoc(fn) or "").strip().split("\n")[0],
            parameters_schema=schema,
            handler=fn,
        )
        return fn

    return deco


def _infer_parameters_schema(fn: Any) -> dict[str, Any]:
    """从函数签名推断 OpenAI function-calling 的 parameters JSON Schema。"""
    sig = inspect.signature(fn)
    try:
        hints = typing.get_type_hints(fn)
    except Exception:  # noqa: BLE001  注解无法解析时退化为无类型
        hints = {}
    props: dict[str, Any] = {}
    required: list[str] = []
    for pname, param in sig.parameters.items():
        if pname in ("self", "cls") or param.kind in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            continue
        hint = hints.get(pname, str)
        json_type = _PY_TO_JSON.get(hint, "string")
        props[pname] = {"type": json_type}
        if param.default is inspect.Parameter.empty:
            required.append(pname)
    schema: dict[str, Any] = {"type": "object", "properties": props}
    if required:
        schema["required"] = required
    return schema
