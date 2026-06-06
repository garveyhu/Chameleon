"""图片可达性工具 —— 远程模型（DashScope 等）服务端要能拉到图片。

本地 MinIO（127.0.0.1）地址远端抓不到，则下载后转 base64 data URI 内联发送
（无需公网桶）。公网地址 / 已是 data: 的原样透传。i2v 首帧、VLM 参考图共用。
"""

from __future__ import annotations

import base64
from urllib.parse import urlparse

import httpx

_LOCAL_HOSTS = ("127.0.0.1", "localhost", "0.0.0.0")


async def ensure_fetchable(url: str) -> str:
    host = urlparse(url).hostname or ""
    if url.startswith("data:") or not any(h in host for h in _LOCAL_HOSTS):
        return url
    async with httpx.AsyncClient(timeout=60.0) as c:
        r = await c.get(url)
    r.raise_for_status()
    mime = (r.headers.get("content-type") or "image/png").split(";")[0]
    return f"data:{mime};base64,{base64.b64encode(r.content).decode()}"
