"""P22.4 PR #81+#82 单测：VLM caption + Hit kind 字段"""

from __future__ import annotations

from chameleon.core.retrieval import (
    Hit,
    HybridConfig,
    generate_caption,
    generate_captions_batch,
    metadata_filter,
)

# ── VLM caption（PR #81） ──────────────────────────────


async def test_generate_caption_with_vlm_callable():
    async def vlm(url: str) -> str:
        return f"图中是一只猫 ({url})"

    result = await generate_caption(
        "https://example.com/cat.jpg", vlm=vlm
    )
    assert "猫" in result.caption
    assert result.image_url == "https://example.com/cat.jpg"
    assert result.source == "vlm"
    assert result.is_fallback is False


async def test_generate_caption_vlm_failure_falls_back_to_text():
    async def vlm(url: str) -> str:
        raise RuntimeError("VLM unavailable")

    result = await generate_caption(
        "https://example.com/x.jpg",
        vlm=vlm,
        fallback_text="客户提供的描述",
    )
    assert result.caption == "客户提供的描述"
    assert result.source == "fallback"
    assert result.is_fallback is True


async def test_generate_caption_no_vlm_uses_fallback_text():
    result = await generate_caption(
        "https://example.com/x.jpg", fallback_text="manual caption"
    )
    assert result.caption == "manual caption"
    assert result.is_fallback is True


async def test_generate_caption_no_vlm_no_fallback_uses_filename():
    result = await generate_caption("https://example.com/path/photo.png")
    assert "photo.png" in result.caption
    assert result.is_fallback is True


async def test_generate_caption_filename_strips_query_string():
    result = await generate_caption(
        "https://example.com/img/foo.jpg?token=abc"
    )
    assert "foo.jpg" in result.caption
    assert "token" not in result.caption


async def test_generate_caption_empty_vlm_response_falls_back():
    async def empty_vlm(url: str) -> str:
        return ""

    result = await generate_caption(
        "https://example.com/x.jpg",
        vlm=empty_vlm,
        fallback_text="fb",
    )
    assert result.caption == "fb"


async def test_generate_captions_batch():
    async def vlm(url: str) -> str:
        return f"cap-{url[-5:]}"

    urls = [
        "https://example.com/a.jpg",
        "https://example.com/b.png",
        "https://example.com/c.gif",
    ]
    results = await generate_captions_batch(urls, vlm=vlm)
    assert len(results) == 3
    assert all(r.source == "vlm" for r in results)


async def test_generate_caption_vlm_client_protocol():
    """支持 VLMClient.caption_image 方法（Protocol 形态）"""

    class FakeClient:
        async def caption_image(self, url: str) -> str:
            return f"client-cap-{url[-3:]}"

    result = await generate_caption(
        "https://example.com/x.jpg", vlm=FakeClient()
    )
    assert result.caption.startswith("client-cap")


# ── multimodal Hit + metadata filter（PR #82） ─────────


def test_image_hit_filtered_when_text_only_kinds():
    """allow_kinds={'text'} 时 image hit 被剔"""
    hits = [
        Hit(chunk_id=1, kind="text", score=0.9),
        Hit(chunk_id=2, kind="image", score=0.9),
    ]
    out = metadata_filter(hits, HybridConfig(allow_kinds={"text"}))
    assert [h.chunk_id for h in out] == [1]


def test_image_hit_kept_when_multimodal_kinds():
    """allow_kinds={'text', 'image'} 时图文都保留"""
    hits = [
        Hit(chunk_id=1, kind="text", score=0.9),
        Hit(chunk_id=2, kind="image", score=0.9),
    ]
    out = metadata_filter(hits, HybridConfig(allow_kinds={"text", "image"}))
    assert {h.chunk_id for h in out} == {1, 2}
