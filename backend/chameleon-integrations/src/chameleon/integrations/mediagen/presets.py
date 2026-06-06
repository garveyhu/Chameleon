"""媒体生成的共享预置 —— 风格库 / 尺寸预置 / 字段助手（叶子模块，无驱动依赖）。

尺寸预置严格按各上游官方 API 支持的取值给出（不同接口范围不同）；面板另提供
「自定义宽高」入口（带官方像素上下限），让预置之外的尺寸也能调。
"""

from __future__ import annotations

from typing import Any

from .types import ParamFieldType

# ── 风格预设库（通用，driver 无关；qwen 无原生 style 参数 → 拼进 prompt）──
STYLE_PRESETS: list[dict[str, Any]] = [
    {"id": "none", "label": "无风格", "suffix": ""},
    {"id": "photographic", "label": "写实摄影", "suffix": "photographic, realistic, ultra detailed, professional photography, 8k"},
    {"id": "cinematic", "label": "电影感", "suffix": "cinematic lighting, film grain, dramatic atmosphere, movie still, shallow depth of field"},
    {"id": "anime", "label": "动漫", "suffix": "anime style, vibrant colors, clean lineart, cel shading"},
    {"id": "illustration", "label": "插画", "suffix": "digital illustration, concept art, flat colors, trending on artstation"},
    {"id": "render3d", "label": "3D 渲染", "suffix": "3D render, octane render, soft studio lighting, subsurface scattering"},
    {"id": "oil", "label": "油画", "suffix": "oil painting, textured brushstrokes, classical fine art"},
    {"id": "watercolor", "label": "水彩", "suffix": "watercolor painting, soft color washes, delicate, paper texture"},
    {"id": "cyberpunk", "label": "赛博朋克", "suffix": "cyberpunk, neon lights, futuristic city, high tech, moody"},
    {"id": "guofeng", "label": "国风", "suffix": "Chinese ink painting style, traditional, elegant, guofeng"},
    {"id": "pixel", "label": "像素风", "suffix": "pixel art, 8-bit, retro game style"},
    {"id": "minimal", "label": "极简", "suffix": "minimalist, clean composition, simple, ample negative space"},
]

# ── 尺寸预置（W*H），严格对齐官方 API ───────────────────────
# qwen-image-2.0 / pro / max（multimodal 同步）：官方枚举，per-dim 上限 2688
ASPECT_MULTIMODAL = [
    {"value": "2048*2048", "label": "1:1"},
    {"value": "2688*1536", "label": "16:9"},
    {"value": "1536*2688", "label": "9:16"},
    {"value": "2368*1728", "label": "4:3"},
    {"value": "1728*2368", "label": "3:4"},
]
MULTIMODAL_DIM = (512, 2688)

# qwen-image / plus、万相 wan（synthesis 异步）：per-dim 上限较小
ASPECT_SYNTHESIS = [
    {"value": "1328*1328", "label": "1:1"},
    {"value": "1664*928", "label": "16:9"},
    {"value": "928*1664", "label": "9:16"},
    {"value": "1472*1140", "label": "4:3"},
    {"value": "1140*1472", "label": "3:4"},
]
SYNTHESIS_DIM = (512, 1664)

# wan 视频分辨率
VIDEO_RESOLUTION = [
    {"value": "720P", "label": "720P"},
    {"value": "1080P", "label": "1080P"},
]


def field(
    key: str,
    label: str,
    ftype: ParamFieldType | str,
    default: Any = None,
    group: str = "basic",
    **extra: Any,
) -> dict[str, Any]:
    """构造一个生成面板字段 spec。"""
    return {
        "key": key,
        "label": label,
        "type": str(ftype),
        "default": default,
        "group": group,
        **extra,
    }
