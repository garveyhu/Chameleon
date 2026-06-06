"""计费单位枚举（集中维护，前后端共识）。

高可扩展：新增计费单位 / 视频分辨率档 = 这里加枚举值 + 价目表加行，无需迁移。
"""

from __future__ import annotations

from enum import StrEnum


class PricingUnit(StrEnum):
    """媒体计费单位。"""

    IMAGE = "image"  # 按张
    VIDEO_SECOND = "video_second"  # 按秒


class VideoTier(StrEnum):
    """视频分辨率分档（MediaPricing.tier 值，与生成参数 resolution 对齐）。"""

    P720 = "720P"
    P1080 = "1080P"
