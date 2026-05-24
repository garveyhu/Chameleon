"""PR B5 单测：ImageEmbedder —— caption → 文本向量"""

from __future__ import annotations

import pytest

from chameleon.core.embedding import image as image_mod
from chameleon.core.embedding.image import ImageEmbedder


class _StubEmbedding:
    model = "stub"
    dim = 3

    async def embed(self, texts: list[str]) -> list[list[float]]:
        # 向量编码 caption 长度，便于断言"caption 被真的 embed"
        return [[float(len(t)), 0.0, 0.0] for t in texts]


@pytest.fixture(autouse=True)
def _patch_embedding(monkeypatch):
    monkeypatch.setattr(
        image_mod, "get_embedding_client", lambda model=None: _StubEmbedding()
    )


async def test_embed_image_with_caption_fn():
    async def caption_fn(url: str) -> str:
        return f"a photo of {url}"

    embedder = ImageEmbedder(embedding_model="stub", caption_fn=caption_fn)
    res = await embedder.embed_image("http://x/cat.png")
    assert res.source == "vlm"
    assert res.caption == "a photo of http://x/cat.png"
    assert res.vector[0] == float(len(res.caption))


async def test_embed_image_explicit_caption_wins():
    async def caption_fn(_url: str) -> str:
        return "from-vlm"

    embedder = ImageEmbedder(embedding_model="stub", caption_fn=caption_fn)
    res = await embedder.embed_image("http://x/a.png", caption="手写说明")
    assert res.source == "explicit"
    assert res.caption == "手写说明"


async def test_embed_image_fallback_to_filename_when_no_caption_fn():
    embedder = ImageEmbedder(embedding_model="stub")
    res = await embedder.embed_image("http://cdn/x/diagram.png?token=abc")
    assert res.source == "fallback"
    # 去 query string + 文件名
    assert res.caption == "[image] diagram.png"


async def test_embed_image_caption_fn_failure_falls_back():
    async def boom(_url: str) -> str:
        raise RuntimeError("vlm down")

    embedder = ImageEmbedder(embedding_model="stub", caption_fn=boom)
    res = await embedder.embed_image("http://x/y.jpg", fallback_text="备用说明")
    assert res.source == "fallback"
    assert res.caption == "备用说明"


async def test_embed_images_batch():
    async def caption_fn(url: str) -> str:
        return url.rsplit("/", 1)[-1]

    embedder = ImageEmbedder(embedding_model="stub", caption_fn=caption_fn)
    out = await embedder.embed_images(["http://x/a.png", "http://x/bb.png"])
    assert [r.caption for r in out] == ["a.png", "bb.png"]
    assert all(r.source == "vlm" for r in out)


async def test_embed_images_empty():
    embedder = ImageEmbedder(embedding_model="stub")
    assert await embedder.embed_images([]) == []
