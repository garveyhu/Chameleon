"""媒体生成驱动注册表 —— 新增厂商：建驱动文件 + 此处 import 一行。"""

from __future__ import annotations

from . import comfyui, dashscope  # noqa: F401  import 即触发 register_driver
from .base import MediaGenDriver, get_driver, register_driver, registered_drivers

__all__ = [
    "MediaGenDriver",
    "get_driver",
    "register_driver",
    "registered_drivers",
    "comfyui",
    "dashscope",
]
