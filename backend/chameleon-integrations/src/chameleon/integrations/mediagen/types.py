"""媒体生成（文生图 / 图生视频 …）的统一类型。

不同后端（本地 ComfyUI / 远程 DashScope …）都被抽象成「驱动 driver」，
共享同一套 MediaTarget（运行目标）与事件协议。新增后端 = 加一个 driver，
不改 resolver / service / 上层调用方。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class MediaKind(StrEnum):
    """生成产物模态。"""

    image = "image"
    video = "video"


class DriverName(StrEnum):
    """媒体生成后端驱动名（与各 driver.name 对应）。"""

    comfyui = "comfyui"
    dashscope = "dashscope"


class MediaApiStyle(StrEnum):
    """DashScope 图片调用接口形态。"""

    synthesis = "synthesis"  # 异步 text2image（qwen-image / plus、万相 wan）
    multimodal = "multimodal"  # 同步 multimodal（qwen-image-2.0 / pro / max）


class ParamFieldType(StrEnum):
    """生成面板字段类型（前后端共用，前端按此渲染控件）。"""

    aspect_ratio = "aspect_ratio"
    select = "select"
    int = "int"
    float = "float"
    text = "text"
    seed = "seed"
    toggle = "toggle"


class MediaConfigError(Exception):
    """媒体生成模型配置不完整 / 不可用（缺驱动、缺上游、缺 key 等）。"""


class MediaGenError(RuntimeError):
    """生成过程失败（上游拒绝 / 任务失败 / 超时）。"""


@dataclass(frozen=True)
class MediaTarget:
    """一次媒体生成调用所需的全部静态配置（由 resolver 从 model+provider 解析）。

    driver:      后端驱动名（"comfyui" / "dashscope" …）
    media_kind:  产物模态（image / video）
    host:        provider.base_url（comfyui 地址 / dashscope compatible base 等）
    api_key:     provider 解密后的 key（comfyui 本地为 None）
    model_code:  本系统 model.code（仅用于日志 / trace 归属）
    upstream:    驱动用的上游标识 —— comfyui=工作流 id；dashscope=上游模型名
    params:      默认参数（尺寸 / 步数 / 分辨率 / 时长 …），调用时可被覆盖
    """

    driver: str
    media_kind: str
    host: str
    api_key: str | None
    model_code: str
    upstream: str
    params: dict[str, Any] = field(default_factory=dict)
    # 厂商专属配置位（来自 provider.extra_config）：region / org / 额外 header 等，
    # 让新厂商无需改 MediaTarget 结构即可携带自定义参数。
    extra: dict[str, Any] = field(default_factory=dict)
