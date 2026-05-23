"""Plugin SDK —— 外部插件开发者使用的装饰器 + 元数据

P19.2 PR #34：MVP 装饰器把 plugin entrypoint 类标记上 manifest，方便：
1. registry 校验 entrypoint 时确认 "确实是被声明为 plugin 的类"
2. 未来 sandbox 注入 service interface 时拿到挂载点

用法示例：
```python
# my_plugin/provider.py
from chameleon.core.plugins.sdk import plugin_provider

@plugin_provider(name="openrouter", version="1.0.0")
class OpenRouterProvider(Provider):
    ...
```

红线（plan §2 新增）：
- ⛔ SDK 只暴露声明性能力（装饰器 + dataclass）；禁止包含数据库 session / 凭据
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, TypeVar

from chameleon.core.plugins.manifest import PluginType

T = TypeVar("T")

_PLUGIN_META_ATTR = "__chameleon_plugin_meta__"


@dataclass(frozen=True)
class PluginMeta:
    """装饰器附加到 plugin 类上的运行时元数据"""

    name: str
    version: str
    type: PluginType
    description: str | None = None


def _make_decorator(plugin_type: PluginType) -> Callable[..., Callable[[type[T]], type[T]]]:
    def decorator_factory(
        *,
        name: str,
        version: str,
        description: str | None = None,
    ) -> Callable[[type[T]], type[T]]:
        if not name:
            raise ValueError("plugin name 不能为空")
        if not version:
            raise ValueError("plugin version 不能为空")

        def decorator(cls: type[T]) -> type[T]:
            meta = PluginMeta(
                name=name,
                version=version,
                type=plugin_type,
                description=description,
            )
            setattr(cls, _PLUGIN_META_ATTR, meta)
            return cls

        return decorator

    return decorator_factory


plugin_provider = _make_decorator("provider")
"""@plugin_provider(name=..., version=...) → 标记 Provider 子类"""

plugin_tool = _make_decorator("tool")
"""@plugin_tool(name=..., version=...) → 标记 Tool 子类"""

plugin_embedding = _make_decorator("embedding")
"""@plugin_embedding(name=..., version=...) → 标记 embedding 类"""


def get_plugin_meta(cls: type) -> PluginMeta | None:
    """读取类上的 plugin 元数据（未装饰返 None）"""
    meta = getattr(cls, _PLUGIN_META_ATTR, None)
    return meta if isinstance(meta, PluginMeta) else None


__all__ = [
    "PluginMeta",
    "plugin_provider",
    "plugin_tool",
    "plugin_embedding",
    "get_plugin_meta",
]
