"""VLM 图片 caption —— P22.4 PR #81

把上传的图片转为可检索的 text caption（入 KB 作为 chunk）。

红线（plan §2 P22）：
- ⛔ caption 走 URL 引用（image_url block）；不内嵌 base64 到 chunk 内容
- ⛔ 失败 fallback 用文件名做最小 caption（保证至少有内容可检索）
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol

from loguru import logger

#: VLM caption_fn 签名：image_url → caption text
CaptionFn = Callable[[str], Awaitable[str]]


@dataclass
class CaptionResult:
    """单图 caption 结果"""

    caption: str
    image_url: str
    source: str = "vlm"  # vlm / fallback / manual

    @property
    def is_fallback(self) -> bool:
        return self.source == "fallback"


class VLMClient(Protocol):
    """VLM 调用客户端协议；调用方实现具体 vendor"""

    async def caption_image(self, image_url: str) -> str:
        ...


async def generate_caption(
    image_url: str,
    *,
    vlm: CaptionFn | VLMClient | None = None,
    fallback_text: str | None = None,
) -> CaptionResult:
    """对 image_url 生成 caption

    优先级：
    1) 显式 vlm callable / client → 调用
    2) 失败或缺失 → fallback_text（admin 提供）/ 文件名最小 caption
    """
    if vlm is not None:
        try:
            if hasattr(vlm, "caption_image"):
                cap = await vlm.caption_image(image_url)  # type: ignore[union-attr]
            else:
                cap = await vlm(image_url)  # type: ignore[misc]
            if cap and cap.strip():
                return CaptionResult(caption=cap.strip(), image_url=image_url)
        except Exception:
            logger.exception(
                "vlm caption failed | url={} | falling back", image_url
            )

    # fallback
    if fallback_text and fallback_text.strip():
        return CaptionResult(
            caption=fallback_text.strip(),
            image_url=image_url,
            source="fallback",
        )

    # 最末 fallback：用 URL 末段文件名
    filename = image_url.rsplit("/", 1)[-1] or image_url
    name_part = filename.rsplit("?", 1)[0]  # 去 query string
    minimal = f"[image] {name_part}"
    return CaptionResult(
        caption=minimal, image_url=image_url, source="fallback"
    )


async def generate_captions_batch(
    image_urls: list[str],
    *,
    vlm: CaptionFn | VLMClient | None = None,
    fallback_texts: dict[str, str] | None = None,
) -> list[CaptionResult]:
    """批量；逐张调用（避免并发把 VLM 配额打爆；并发由调用方控）"""
    out: list[CaptionResult] = []
    for url in image_urls:
        fb = (fallback_texts or {}).get(url)
        cap = await generate_caption(url, vlm=vlm, fallback_text=fb)
        out.append(cap)
    return out
