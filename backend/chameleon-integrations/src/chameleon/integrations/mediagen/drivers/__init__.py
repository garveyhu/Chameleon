"""媒体生成驱动注册表 —— 新增后端在此登记一行即可。"""

from __future__ import annotations

from ..types import MediaConfigError
from .base import MediaGenDriver
from .comfyui import ComfyUIDriver
from .dashscope import DashScopeDriver

_DRIVERS: dict[str, MediaGenDriver] = {
    d.name: d for d in (ComfyUIDriver(), DashScopeDriver())
}


def get_driver(name: str) -> MediaGenDriver:
    driver = _DRIVERS.get(name)
    if driver is None:
        raise MediaConfigError(
            f"未知媒体生成驱动: {name!r}（已注册: {sorted(_DRIVERS)}）"
        )
    return driver


def registered_drivers() -> list[str]:
    return sorted(_DRIVERS)


__all__ = ["MediaGenDriver", "get_driver", "registered_drivers"]
