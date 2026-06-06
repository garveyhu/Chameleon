"""生图编排 service：拼工作流 → 提交 ComfyUI → 轮询 → 取图存 MinIO。

核心是异步生成器 ``stream_generate``，逐步 yield 进度事件，最后一个 ``done`` 事件带
MinIO 产物 URL。测试端点（SSE 进度）与未来的智能体 / 工作流调用都复用它——
后者只需消费到最后的 ``done`` 取 ``image_url`` 即可。
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from typing import Any

from loguru import logger

from chameleon.data.infra.object_store import get_object_store

from .comfyui_client import ComfyUIClient, ComfyUIError
from .workflows import build_workflow

_CONTENT_TYPE = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
}


def _first_image(outputs: dict[str, Any]) -> dict[str, Any] | None:
    """从 history 的 outputs 里取第一张图片元信息。"""
    for out in outputs.values():
        for img in out.get("images", []) or []:
            return img
    return None


async def stream_generate(
    *,
    host: str,
    workflow_id: str,
    prompt: str,
    params: dict[str, Any] | None = None,
    poll_interval: float = 2.0,
    timeout: float = 600.0,
) -> AsyncIterator[dict[str, Any]]:
    """提交一次生图并流式 yield 进度。

    事件类型：
      - ``{"type": "submitted", "prompt_id": str}``
      - ``{"type": "progress", "elapsed_ms": int}``
      - ``{"type": "done", "image_url": str, "image_key": str,
            "filename": str, "latency_ms": int}``

    Raises:
        ComfyUIError: 提交被拒 / 执行失败
        TimeoutError: 超过 timeout 仍未产出
    """
    client = ComfyUIClient(host, timeout=timeout)
    workflow = build_workflow(workflow_id, prompt=prompt, params=params)

    prompt_id = await client.submit(workflow)
    logger.info("imagegen submitted | prompt_id={} workflow={}", prompt_id, workflow_id)
    yield {"type": "submitted", "prompt_id": prompt_id}

    start = time.monotonic()
    img_meta: dict[str, Any] | None = None
    while True:
        entry = await client.history(prompt_id)
        if entry:
            status = entry.get("status", {})
            if status.get("status_str") == "error":
                msgs = status.get("messages", [])
                raise ComfyUIError(f"ComfyUI 执行失败: {msgs}")
            img_meta = _first_image(entry.get("outputs", {}))
            if img_meta:
                break
        elapsed = time.monotonic() - start
        if elapsed > timeout:
            raise TimeoutError(f"生图超时（>{timeout:.0f}s），prompt_id={prompt_id}")
        yield {"type": "progress", "elapsed_ms": int(elapsed * 1000)}
        await asyncio.sleep(poll_interval)

    filename = img_meta["filename"]
    data = await client.view_bytes(
        filename, img_meta.get("subfolder", ""), img_meta.get("type", "output")
    )

    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "png"
    content_type = _CONTENT_TYPE.get(ext, "image/png")
    key = f"imagegen/{prompt_id}/{filename}"
    store = get_object_store()
    await asyncio.to_thread(store.put, key, data, content_type=content_type)
    image_url = store.presigned_get_url(key)

    latency_ms = int((time.monotonic() - start) * 1000)
    logger.info(
        "imagegen done | prompt_id={} key={} bytes={} latency_ms={}",
        prompt_id,
        key,
        len(data),
        latency_ms,
    )
    yield {
        "type": "done",
        "image_url": image_url,
        "image_key": key,
        "filename": filename,
        "latency_ms": latency_ms,
    }
