"""多模态生成集成（文生图 / 图生视频 …，多后端驱动）。"""

from .drivers import get_driver, registered_drivers
from .fetch import ensure_fetchable
from .param_specs import build_param_spec
from .presets import STYLE_PRESETS
from .resolver import build_media_target, resolve_media_target
from .service import stream_generate
from .types import (
    DriverName,
    MediaApiStyle,
    MediaConfigError,
    MediaGenError,
    MediaKind,
    MediaTarget,
    ParamFieldType,
)
from .workflows import build_workflow, list_workflows, workflow_exists

__all__ = [
    "MediaKind",
    "MediaTarget",
    "DriverName",
    "MediaApiStyle",
    "ParamFieldType",
    "MediaConfigError",
    "MediaGenError",
    "build_media_target",
    "resolve_media_target",
    "build_param_spec",
    "ensure_fetchable",
    "STYLE_PRESETS",
    "stream_generate",
    "get_driver",
    "registered_drivers",
    "build_workflow",
    "list_workflows",
    "workflow_exists",
]
