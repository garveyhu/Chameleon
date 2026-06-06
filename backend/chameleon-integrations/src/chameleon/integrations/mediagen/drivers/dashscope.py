"""DashScope（阿里百炼）驱动 —— 远程生成，两种调用形态。

图片：
  - 同步 multimodal：``/api/v1/services/aigc/multimodal-generation/generation``
    （qwen-image-2.0 / 2.0-pro / max 系；无 async 头、直接返结果）
  - 异步 synthesis：``/api/v1/services/aigc/text2image/image-synthesis``
    （qwen-image / qwen-image-plus、万相 wan t2i；X-DashScope-Async + 轮询）
视频：``/api/v1/services/aigc/video-generation/video-synthesis``（wan i2v，P2 接入）

模型用哪条由 ``model.defaults.api`` 指定（multimodal / synthesis），缺省 synthesis。
两条路径拿到产物 url 后都走 ``_download_and_store`` 落 MinIO。
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx
from loguru import logger

from ..persist import content_type_for, store_media
from ..types import MediaConfigError, MediaGenError, MediaTarget

_POLL_INTERVAL = 3.0
_IMAGE_TIMEOUT = 300.0
_SYNC_TIMEOUT = 240.0
_TERMINAL_FAIL = {"FAILED", "CANCELED", "UNKNOWN"}


def _root(host: str) -> str:
    """从 provider base_url 推 DashScope 根（剥掉 compatible-mode 段）。"""
    base = (host or "https://dashscope.aliyuncs.com").split("/compatible-mode")[0]
    return base.rstrip("/")


def _filename_from_url(url: str, fallback: str) -> str:
    seg = url.split("?")[0].rstrip("/").rsplit("/", 1)[-1]
    return seg if "." in seg else fallback


def _extract_media_url(output: dict[str, Any]) -> str | None:
    """从结果取产物 url —— 兼容 messages(choices) 与 results 两种风格。"""
    for ch in output.get("choices") or []:
        for blk in (ch.get("message", {}) or {}).get("content") or []:
            if isinstance(blk, dict):
                for k in ("image", "video", "url"):
                    if blk.get(k):
                        return blk[k]
    for res in output.get("results") or []:
        if isinstance(res, dict):
            for k in ("url", "video_url"):
                if res.get(k):
                    return res[k]
    vid = output.get("video_url")
    return vid if isinstance(vid, str) else None


class DashScopeDriver:
    name = "dashscope"

    async def generate(
        self,
        target: MediaTarget,
        *,
        prompt: str,
        params: dict[str, Any],
        input_images: list[str],
    ) -> AsyncIterator[dict[str, Any]]:
        if not target.api_key:
            raise MediaConfigError("DashScope 供应商未配置 api_key")
        if target.media_kind == "image":
            async for ev in self._image(target, prompt, params):
                yield ev
        elif target.media_kind == "video":
            async for ev in self._video(target, prompt, params, input_images):
                yield ev
        else:
            raise MediaConfigError(f"DashScope 驱动不支持模态: {target.media_kind}")

    # ── 文生图 ──────────────────────────────────────────────
    async def _image(
        self, target: MediaTarget, prompt: str, params: dict[str, Any]
    ) -> AsyncIterator[dict[str, Any]]:
        merged = {**target.params, **(params or {})}
        size = str(merged.get("size") or "1328*1328")
        root = _root(target.host)
        api_style = str(merged.get("api") or "synthesis")
        if api_style == "multimodal":
            endpoint = f"{root}/api/v1/services/aigc/multimodal-generation/generation"
            body: dict[str, Any] = {
                "model": target.upstream,
                "input": {"messages": [{"role": "user", "content": [{"text": prompt}]}]},
                "parameters": {
                    "size": size,
                    "n": 1,
                    "watermark": False,
                    "prompt_extend": True,
                },
            }
            async for ev in self._sync_task(target, endpoint, body, "image", _SYNC_TIMEOUT):
                yield ev
        else:
            endpoint = f"{root}/api/v1/services/aigc/text2image/image-synthesis"
            body = {
                "model": target.upstream,
                "input": {"prompt": prompt},
                "parameters": {"size": size, "n": 1, "watermark": False},
            }
            async for ev in self._async_task(target, endpoint, body, "image", _IMAGE_TIMEOUT):
                yield ev

    # ── 图生视频（P2 实装上游字段，先留接口形态）───────────────
    async def _video(
        self,
        target: MediaTarget,
        prompt: str,
        params: dict[str, Any],
        input_images: list[str],
    ) -> AsyncIterator[dict[str, Any]]:
        raise MediaConfigError("DashScope 视频驱动将在 P2 接入")
        yield {}  # pragma: no cover  (让本方法成为 async generator)

    # ── 同步调用（multimodal）：POST 直接返结果，无轮询 ─────────
    async def _sync_task(
        self,
        target: MediaTarget,
        endpoint: str,
        body: dict[str, Any],
        media_kind: str,
        timeout: float,
    ) -> AsyncIterator[dict[str, Any]]:
        headers = {
            "Authorization": f"Bearer {target.api_key}",
            "Content-Type": "application/json",
        }
        yield {"type": "submitted", "ref": ""}
        start = time.monotonic()
        async with httpx.AsyncClient(timeout=timeout) as c:
            resp = await c.post(endpoint, headers=headers, json=body)
        if resp.status_code != 200:
            logger.error("dashscope sync rejected: {} {}", resp.status_code, resp.text)
            raise MediaGenError(f"DashScope 调用失败 (HTTP {resp.status_code}): {resp.text}")
        output = resp.json().get("output") or {}
        media_url = _extract_media_url(output)
        if not media_url:
            raise MediaGenError(f"DashScope 无产物 url: {output}")
        yield await self._download_and_store(media_url, "sync", media_kind, start)

    # ── 异步任务（synthesis / video）：提交→轮询→下载 ──────────
    async def _async_task(
        self,
        target: MediaTarget,
        endpoint: str,
        body: dict[str, Any],
        media_kind: str,
        timeout: float,
    ) -> AsyncIterator[dict[str, Any]]:
        root = _root(target.host)
        auth = {"Authorization": f"Bearer {target.api_key}"}
        submit_headers = {**auth, "Content-Type": "application/json", "X-DashScope-Async": "enable"}

        async with httpx.AsyncClient(timeout=60.0) as c:
            resp = await c.post(endpoint, headers=submit_headers, json=body)
        if resp.status_code != 200:
            logger.error("dashscope submit rejected: {} {}", resp.status_code, resp.text)
            raise MediaGenError(f"DashScope 提交失败 (HTTP {resp.status_code}): {resp.text}")
        task_id = (resp.json().get("output") or {}).get("task_id")
        if not task_id:
            raise MediaGenError(f"DashScope 未返回 task_id: {resp.text}")
        logger.info("mediagen dashscope submitted | task_id={} model={}", task_id, target.upstream)
        yield {"type": "submitted", "ref": task_id}

        start = time.monotonic()
        media_url: str | None = None
        poll_url = f"{root}/api/v1/tasks/{task_id}"
        while True:
            async with httpx.AsyncClient(timeout=60.0) as c:
                pr = await c.get(poll_url, headers=auth)
            pr.raise_for_status()
            output = pr.json().get("output") or {}
            status = output.get("task_status")
            if status == "SUCCEEDED":
                media_url = _extract_media_url(output)
                if not media_url:
                    raise MediaGenError(f"DashScope 任务成功但无产物 url: {output}")
                break
            if status in _TERMINAL_FAIL:
                raise MediaGenError(f"DashScope 任务失败({status}): {output}")
            elapsed = time.monotonic() - start
            if elapsed > timeout:
                raise TimeoutError(f"DashScope 生成超时（>{timeout:.0f}s），task_id={task_id}")
            yield {"type": "progress", "elapsed_ms": int(elapsed * 1000)}
            await asyncio.sleep(_POLL_INTERVAL)

        yield await self._download_and_store(media_url, task_id, media_kind, start)

    # ── 下载产物落 MinIO ──────────────────────────────────────
    async def _download_and_store(
        self, media_url: str, ref: str, media_kind: str, start: float
    ) -> dict[str, Any]:
        ext_default = "mp4" if media_kind == "video" else "png"
        async with httpx.AsyncClient(timeout=180.0) as c:
            dr = await c.get(media_url)
        dr.raise_for_status()
        data = dr.content
        filename = _filename_from_url(media_url, f"{ref}.{ext_default}")
        content_type = content_type_for(
            filename, "video/mp4" if media_kind == "video" else "image/png"
        )
        key, url = await store_media(data, ref=ref, filename=filename, content_type=content_type)
        latency_ms = int((time.monotonic() - start) * 1000)
        logger.info("mediagen dashscope done | key={} bytes={} latency_ms={}", key, len(data), latency_ms)
        return {
            "type": "done",
            "url": url,
            "key": key,
            "media_kind": media_kind,
            "mime_type": content_type,
            "filename": filename,
            "latency_ms": latency_ms,
        }
