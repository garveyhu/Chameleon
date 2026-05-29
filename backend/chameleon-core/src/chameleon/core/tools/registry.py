"""全局 Tool registry —— 类似 provider / agent registry

启动时各 builtin 模块 import 触发 register_tool(); 业务侧调 get_tool(key)。
"""

from __future__ import annotations

from chameleon.core.tools.base import Tool

_REGISTRY: dict[str, type[Tool]] = {}


def register_tool(cls: type[Tool]) -> type[Tool]:
    """装饰器 / 函数：注册 Tool 子类到全局 registry

    用法（在 builtins/xxx.py 末尾）：
        register_tool(MyTool)
    """
    if not cls.tool_key:
        raise ValueError(
            f"{cls.__name__} 缺少 tool_key 类属性"
        )
    if cls.tool_key in _REGISTRY and _REGISTRY[cls.tool_key] is not cls:
        raise ValueError(
            f"tool_key={cls.tool_key!r} 已注册为 "
            f"{_REGISTRY[cls.tool_key].__name__}，不能再注册 {cls.__name__}"
        )
    _REGISTRY[cls.tool_key] = cls
    return cls


def get_tool_class(tool_key: str) -> type[Tool] | None:
    return _REGISTRY.get(tool_key)


def list_tool_keys() -> list[str]:
    return sorted(_REGISTRY.keys())


def all_tool_classes() -> dict[str, type[Tool]]:
    """返 registry 浅拷贝"""
    return dict(_REGISTRY)
