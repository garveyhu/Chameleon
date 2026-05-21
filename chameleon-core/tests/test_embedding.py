"""embedding client 单测"""

import respx
from httpx import Response

from chameleon.core.embedding.openai_compat import OpenAICompatEmbedding


async def test_embed_basic(respx_mock) -> None:
    respx_mock.post("https://api.test/v1/embeddings").mock(
        return_value=Response(
            200,
            json={
                "data": [
                    {"embedding": [0.1] * 4},
                    {"embedding": [0.2] * 4},
                ]
            },
        )
    )
    client = OpenAICompatEmbedding(
        base_url="https://api.test/v1",
        api_key="sk-test",
        model="test-emb",
        dim=4,
    )
    vecs = await client.embed(["hello", "world"])
    assert len(vecs) == 2
    assert vecs[0] == [0.1, 0.1, 0.1, 0.1]


async def test_embed_empty_returns_empty() -> None:
    client = OpenAICompatEmbedding(
        base_url="https://x/v1",
        api_key="k",
        model="m",
        dim=4,
    )
    assert await client.embed([]) == []


async def test_embed_batch_splits(respx_mock) -> None:
    """超 batch_size 自动分批"""
    route = respx_mock.post("https://api.test/v1/embeddings").mock(
        return_value=Response(
            200,
            json={"data": [{"embedding": [0.0] * 4} for _ in range(3)]},
        )
    )
    client = OpenAICompatEmbedding(
        base_url="https://api.test/v1",
        api_key="sk",
        model="m",
        dim=4,
        batch_size=3,
    )
    # 7 条 → 3 个请求（3+3+1）
    route.side_effect = [
        Response(200, json={"data": [{"embedding": [0.0] * 4} for _ in range(3)]}),
        Response(200, json={"data": [{"embedding": [0.0] * 4} for _ in range(3)]}),
        Response(200, json={"data": [{"embedding": [0.0] * 4}]}),
    ]
    vecs = await client.embed(["x"] * 7)
    assert len(vecs) == 7
    assert len(route.calls) == 3


async def test_embed_401_raises_auth(respx_mock) -> None:
    from chameleon.core.api.exceptions import ProviderAuthError

    respx_mock.post("https://api.test/v1/embeddings").mock(
        return_value=Response(401, text='{"err":"invalid"}')
    )
    client = OpenAICompatEmbedding(
        base_url="https://api.test/v1",
        api_key="sk-bad",
        model="m",
        dim=4,
    )
    try:
        await client.embed(["x"])
    except ProviderAuthError:
        pass
    else:
        raise AssertionError("expected ProviderAuthError")


async def test_embed_dim_mismatch(respx_mock) -> None:
    """服务端返了 8 维但配置 4 维 → fail-fast"""
    from chameleon.core.api.exceptions import ProviderInternalError

    respx_mock.post("https://api.test/v1/embeddings").mock(
        return_value=Response(200, json={"data": [{"embedding": [0.1] * 8}]})
    )
    client = OpenAICompatEmbedding(
        base_url="https://api.test/v1",
        api_key="k",
        model="m",
        dim=4,
    )
    try:
        await client.embed(["x"])
    except ProviderInternalError as e:
        assert "dim mismatch" in str(e.message)
    else:
        raise AssertionError("expected ProviderInternalError")


_ = respx  # 保持 import
