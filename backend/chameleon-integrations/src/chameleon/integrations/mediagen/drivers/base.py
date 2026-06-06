"""媒体生成驱动协议 + 注册表。

一个驱动 = 一个厂商/后端的完整实现，**所有厂商差异内聚在驱动类里**：
  - name / supported_kinds：身份与能力声明
  - generate()：生成并落 MinIO，逐步 yield 进度/完成事件
  - param_spec()：该驱动该模态的可调参数（面板按此动态渲染）

新增厂商 = 新建一个驱动文件 + 文件末尾 ``register_driver(YourDriver)`` +
在 ``drivers/__init__.py`` import 一行。无需改 resolver / service / 面板 / 端点。

generate() 事件协议：
  - {"type": "submitted", "ref": str}
  - {"type": "progress", "elapsed_ms": int}
  - {"type": "done", "url","key","media_kind","mime_type","filename","latency_ms"}
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Protocol, runtime_checkable

from ..types import MediaConfigError, MediaTarget


@runtime_checkable
class MediaGenDriver(Protocol):
    """一个后端（ComfyUI / DashScope / 未来厂商）的生成实现。"""

    name: str
    supported_kinds: frozenset[str]

    def generate(
        self,
        target: MediaTarget,
        *,
        prompt: str,
        params: dict[str, Any],
        input_images: list[str],
    ) -> AsyncIterator[dict[str, Any]]:
        """生成产物（异步生成器，逐步 yield 进度/完成事件）。"""
        ...

    def param_spec(self, target: MediaTarget) -> list[dict[str, Any]]:
        """该驱动 + 该模型的可调参数字段（生成面板据此渲染）。"""
        ...


_DRIVERS: dict[str, MediaGenDriver] = {}


def register_driver(cls: type) -> type:
    """类装饰器 / 函数：实例化并登记一个驱动。"""
    inst = cls()
    if inst.name in _DRIVERS and type(_DRIVERS[inst.name]) is not cls:
        raise ValueError(f"媒体生成驱动重名: {inst.name!r}")
    _DRIVERS[inst.name] = inst  # type: ignore[assignment]
    return cls


def get_driver(name: str) -> MediaGenDriver:
    driver = _DRIVERS.get(name)
    if driver is None:
        raise MediaConfigError(
            f"未知媒体生成驱动: {name!r}（已注册: {sorted(_DRIVERS)}）"
        )
    return driver


def registered_drivers() -> list[str]:
    return sorted(_DRIVERS)
