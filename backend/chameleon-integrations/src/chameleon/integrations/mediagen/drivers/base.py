"""媒体生成驱动协议。

驱动只管「按目标生成产物并落 MinIO」，逐步 yield 进度事件：
  - {"type": "submitted", "ref": str}              # 任务已提交（task_id / prompt_id）
  - {"type": "progress", "elapsed_ms": int}        # 轮询中
  - {"type": "done", "url": str, "key": str,       # 产物 presigned url + MinIO key
     "media_kind": "image"|"video", "mime_type": str,
     "filename": str, "latency_ms": int}
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Protocol, runtime_checkable

from ..types import MediaTarget


@runtime_checkable
class MediaGenDriver(Protocol):
    """一个后端（ComfyUI / DashScope …）的生成实现。"""

    name: str

    def generate(
        self,
        target: MediaTarget,
        *,
        prompt: str,
        params: dict[str, Any],
        input_images: list[str],
    ) -> AsyncIterator[dict[str, Any]]:
        """生成产物（异步生成器，逐步 yield 进度/完成事件）。

        Args:
            target: 运行目标（host / api_key / upstream / 默认参数）
            prompt: 文本提示词
            params: 覆盖 target.params 的运行期参数
            input_images: 参考/首帧图片 url（i2v、图编辑用；纯文生图为空）
        """
        ...
