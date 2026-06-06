"""媒体生成编排入口 —— 按驱动分派，逐步 yield 进度/完成事件。

模型测试端点、工作流 image/video 节点、媒体生成 provider 都复用 ``stream_generate``：
消费到最后的 ``done`` 取 ``url`` 即产物。具体后端差异封装在各 driver 内。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from .drivers import get_driver
from .types import MediaTarget


async def stream_generate(
    target: MediaTarget,
    *,
    prompt: str,
    params: dict[str, Any] | None = None,
    input_images: list[str] | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """对一个运行目标发起生成。

    事件：``submitted`` / ``progress`` / ``done``（见 drivers/base.py 协议）。
    """
    driver = get_driver(target.driver)
    async for ev in driver.generate(
        target,
        prompt=prompt,
        params=params or {},
        input_images=input_images or [],
    ):
        yield ev
