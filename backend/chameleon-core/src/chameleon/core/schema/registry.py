"""全局 Pydantic 模型注册表

业务模块用 `@register("xxx")` 装饰器把自己的配置 / 入参 / 出参 Pydantic 类
登记到全局表；admin API 通过 name 查询返给前端。

线程安全：注册发生在 import 时（单线程），运行时只读，无需加锁。
"""

from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

_REGISTRY: dict[str, type[BaseModel]] = {}


def register(name: str):
    """注册 Pydantic 模型到全局 schema 表。

    用法：
        @register("provider.dify.config")
        class DifyProviderConfig(BaseModel):
            base_url: str
            ...

    name 约定：`<domain>.<sub_domain>.<purpose>`，例如：
        - "provider.dify.config"
        - "agent.echo.input"
        - "kb.chunking_strategy.token"

    重复注册同名 schema 抛 ValueError；这是设计上的强约束，防止上下游写错。
    """

    def decorator(cls: type[T]) -> type[T]:
        if not issubclass(cls, BaseModel):
            raise TypeError(
                f"register('{name}') 只能用于 pydantic.BaseModel 子类，"
                f"传入的是 {cls!r}"
            )
        if name in _REGISTRY and _REGISTRY[name] is not cls:
            existing = _REGISTRY[name]
            raise ValueError(
                f"schema name '{name}' 已被 {existing.__module__}.{existing.__name__} "
                f"占用，新注册 {cls.__module__}.{cls.__name__} 拒绝"
            )
        _REGISTRY[name] = cls
        return cls

    return decorator


def get(name: str) -> type[BaseModel] | None:
    """按 name 查 Pydantic 类；查不到返 None。"""
    return _REGISTRY.get(name)


def list_all() -> dict[str, type[BaseModel]]:
    """列出所有已注册的 name → 类映射（返副本，外部修改不影响内部）。"""
    return dict(_REGISTRY)


def _reset_for_tests() -> None:
    """测试用：清空 registry。生产代码勿调。"""
    _REGISTRY.clear()
