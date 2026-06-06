"""ComfyUI 驱动 —— 本地工作流出图（提交→轮询 history→/view 取字节→落 MinIO）。"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from typing import Any

from loguru import logger

from ..comfyui_client import ComfyUIClient
from ..persist import content_type_for, store_media
from ..presets import field
from ..types import MediaGenError, MediaTarget, ParamFieldType
from ..workflows import build_workflow, list_workflows
from .base import register_driver

_POLL_INTERVAL = 2.0
_TIMEOUT = 600.0


def _first_image(outputs: dict[str, Any]) -> dict[str, Any] | None:
    for out in outputs.values():
        for img in out.get("images", []) or []:
            return img
    return None


@register_driver
class ComfyUIDriver:
    name = "comfyui"
    supported_kinds = frozenset({"image"})

    def param_spec(self, target: MediaTarget) -> list[dict[str, Any]]:
        """从工作流的参数 spec 派生：width/height 基础，steps/cfg/seed 高级。"""
        by_id = {w["id"]: w["params"] for w in list_workflows()}
        out: list[dict[str, Any]] = []
        for p in by_id.get(target.upstream, []):
            group = "basic" if p["key"] in ("width", "height") else "advanced"
            ftype = ParamFieldType.int if p.get("type") == "int" else ParamFieldType.float
            out.append(field(p["key"], p["label"], ftype, p.get("default"), group))
        return out

    async def generate(
        self,
        target: MediaTarget,
        *,
        prompt: str,
        params: dict[str, Any],
        input_images: list[str],
    ) -> AsyncIterator[dict[str, Any]]:
        client = ComfyUIClient(target.host, timeout=_TIMEOUT)
        merged = {**target.params, **(params or {})}
        workflow = build_workflow(target.upstream, prompt=prompt, params=merged)

        prompt_id = await client.submit(workflow)
        logger.info("mediagen comfyui submitted | prompt_id={} workflow={}", prompt_id, target.upstream)
        yield {"type": "submitted", "ref": prompt_id}

        start = time.monotonic()
        img_meta: dict[str, Any] | None = None
        while True:
            entry = await client.history(prompt_id)
            if entry:
                status = entry.get("status", {})
                if status.get("status_str") == "error":
                    raise MediaGenError(f"ComfyUI 执行失败: {status.get('messages')}")
                img_meta = _first_image(entry.get("outputs", {}))
                if img_meta:
                    break
            elapsed = time.monotonic() - start
            if elapsed > _TIMEOUT:
                raise TimeoutError(f"出图超时（>{_TIMEOUT:.0f}s），prompt_id={prompt_id}")
            yield {"type": "progress", "elapsed_ms": int(elapsed * 1000)}
            await asyncio.sleep(_POLL_INTERVAL)

        filename = img_meta["filename"]
        data = await client.view_bytes(
            filename, img_meta.get("subfolder", ""), img_meta.get("type", "output")
        )
        content_type = content_type_for(filename, "image/png")
        key, url = await store_media(
            data, ref=prompt_id, filename=filename, content_type=content_type
        )
        latency_ms = int((time.monotonic() - start) * 1000)
        logger.info("mediagen comfyui done | key={} bytes={} latency_ms={}", key, len(data), latency_ms)
        yield {
            "type": "done",
            "url": url,
            "key": key,
            "media_kind": "image",
            "mime_type": content_type,
            "filename": filename,
            "latency_ms": latency_ms,
        }
