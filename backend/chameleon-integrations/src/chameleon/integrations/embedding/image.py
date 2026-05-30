"""图片 embedding —— v1.1 PR B5

约束（坚持单 PG + pgvector 全局 1536 维）：图片不走独立 CLIP 多模态向量列，
而是「caption → 文本 embedding」落进同一 chunks.embedding 向量空间，使图片
chunk 与文本 chunk 在同一空间内可被同一次向量检索召回。

流程：image_url → caption（VLM 或注入的 caption_fn；失败回退文件名）→ 文本
embedding → 1536 维向量。caption 同时作为 chunk.content 入库（可读、可 BM25）。

红线（plan §2 P22）：
- ⛔ 不内嵌 base64 进 chunk；caption 走文件名 / VLM 文本
- ⛔ caption_fn 失败 fallback 文件名最小 caption（保证至少有内容可检索）

本模块不 import core.retrieval（避免 embedding ↔ retrieval 环）；VLM caption
能力由调用方（ingest）注入 caption_fn。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from loguru import logger

from chameleon.integrations.embedding.factory import get_embedding_client

#: caption_fn 签名：image_url → caption text
CaptionFn = Callable[[str], Awaitable[str]]


@dataclass
class ImageEmbedResult:
    """单图 embedding 结果"""

    image_url: str
    caption: str
    vector: list[float]
    #: caption 来源：vlm / explicit / fallback
    source: str


def _fallback_caption(image_url: str) -> str:
    """末位 fallback：用 URL 末段文件名做最小 caption"""
    filename = image_url.rsplit("/", 1)[-1] or image_url
    name_part = filename.rsplit("?", 1)[0]  # 去 query string
    return f"[image] {name_part}"


class ImageEmbedder:
    """图片 → caption → 文本向量"""

    def __init__(
        self,
        *,
        embedding_model: str | None = None,
        caption_fn: CaptionFn | None = None,
    ) -> None:
        self.embedding_model = embedding_model
        self.caption_fn = caption_fn

    async def _resolve_caption(
        self, image_url: str, *, caption: str | None, fallback_text: str | None
    ) -> tuple[str, str]:
        """返 (caption, source)；优先级：显式 caption > caption_fn > fallback_text > 文件名"""
        if caption and caption.strip():
            return caption.strip(), "explicit"
        if self.caption_fn is not None:
            try:
                cap = await self.caption_fn(image_url)
                if cap and cap.strip():
                    return cap.strip(), "vlm"
            except Exception:
                logger.exception("image caption_fn failed | url={}", image_url)
        if fallback_text and fallback_text.strip():
            return fallback_text.strip(), "fallback"
        return _fallback_caption(image_url), "fallback"

    async def embed_image(
        self,
        image_url: str,
        *,
        caption: str | None = None,
        fallback_text: str | None = None,
    ) -> ImageEmbedResult:
        """对单图生成 caption + 文本向量"""
        cap, source = await self._resolve_caption(
            image_url, caption=caption, fallback_text=fallback_text
        )
        client = get_embedding_client(self.embedding_model)
        vecs = await client.embed([cap])
        if not vecs:
            raise RuntimeError(f"image caption embed returned empty | url={image_url}")
        return ImageEmbedResult(
            image_url=image_url, caption=cap, vector=vecs[0], source=source
        )

    async def embed_images(
        self,
        image_urls: list[str],
        *,
        captions: dict[str, str] | None = None,
        fallback_texts: dict[str, str] | None = None,
    ) -> list[ImageEmbedResult]:
        """批量；逐张 caption（避免并发打爆 VLM 配额），caption 文本批量 embed"""
        captions = captions or {}
        fallback_texts = fallback_texts or {}
        resolved: list[tuple[str, str, str]] = []  # (url, caption, source)
        for url in image_urls:
            cap, source = await self._resolve_caption(
                url, caption=captions.get(url), fallback_text=fallback_texts.get(url)
            )
            resolved.append((url, cap, source))

        if not resolved:
            return []
        client = get_embedding_client(self.embedding_model)
        vectors = await client.embed([cap for _, cap, _ in resolved])
        return [
            ImageEmbedResult(
                image_url=url, caption=cap, vector=vec, source=source
            )
            for (url, cap, source), vec in zip(resolved, vectors, strict=True)
        ]
