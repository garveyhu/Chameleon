"""媒体生成参数规约编排 —— 委托给驱动产出字段，附加通用风格库。

字段定义内聚在各驱动的 ``param_spec()``（厂商差异随驱动走）；本模块只负责把
驱动字段与 driver 无关的风格预设拼成面板所需的完整 spec。
"""

from __future__ import annotations

from typing import Any

from .drivers import get_driver
from .presets import STYLE_PRESETS
from .types import MediaTarget


def build_param_spec(target: MediaTarget) -> dict[str, Any]:
    """按运行目标产出 {media_kind, fields, styles}。"""
    fields = get_driver(target.driver).param_spec(target)
    styles = STYLE_PRESETS if target.media_kind in ("image", "video") else []
    return {"media_kind": target.media_kind, "fields": fields, "styles": styles}
