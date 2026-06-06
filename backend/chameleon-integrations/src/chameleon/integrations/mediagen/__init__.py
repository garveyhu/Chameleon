"""多模态生成集成（文生图 / 图生视频 …，多后端驱动）。"""

from .drivers import get_driver, registered_drivers
from .resolver import build_media_target, resolve_media_target
from .service import stream_generate
from .types import MediaConfigError, MediaGenError, MediaKind, MediaTarget
from .workflows import build_workflow, list_workflows, workflow_exists

__all__ = [
    "MediaKind",
    "MediaTarget",
    "MediaConfigError",
    "MediaGenError",
    "build_media_target",
    "resolve_media_target",
    "stream_generate",
    "get_driver",
    "registered_drivers",
    "build_workflow",
    "list_workflows",
    "workflow_exists",
]
