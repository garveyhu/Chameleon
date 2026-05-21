"""跨包集成测试 fixtures

- 注入 mock provider + agent 到 registry
- 注入 DeterministicHashEmbedding 替代真实 OpenAI 调用
"""

from __future__ import annotations

import hashlib
import math
import secrets
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from chameleon.app.main import create_app
from chameleon.core.embedding import set_for_test as set_embedding_for_test
from chameleon.core.infra.db import AsyncSessionLocal
from chameleon.core.infra.jwt import init_jwt
from chameleon.core.utils.crypto import init_crypto
from chameleon.core.models import (
    ApiKey,
    App,
    CallLog,
    Chunk,
    Conversation,
    Document,
    KnowledgeBase,
    Message,
    Task,
)
from chameleon.system.api_key.schemas import CreateApiKeyRequest
from chameleon.system.api_key.service import create_api_key
from chameleon.providers.base import AGENTS, PROVIDERS, init_registry
from chameleon.providers.base.protocol import Provider
from chameleon.providers.base.types import (
    AgentDef,
    InvokeContext,
    StreamEvent,
    StreamEventType,
)

# ── Mock Provider 注入 ──────────────────────────────────


class _MockEchoProvider(Provider):
    """注册名 mock。stream 产 1 个 step + 2 个 delta + done。"""

    name = "mock"

    async def stream(self, ctx: InvokeContext) -> AsyncIterator[StreamEvent]:
        yield StreamEvent(
            type=StreamEventType.step,
            data={"name": "intent_route", "status": "success", "duration_ms": 5},
        )
        text = (
            ctx.input
            if isinstance(ctx.input, str)
            else (ctx.input[-1].content if ctx.input else "")
        )
        yield StreamEvent(type=StreamEventType.delta, data={"text": "echo: "})
        yield StreamEvent(type=StreamEventType.delta, data={"text": text})
        yield StreamEvent(
            type=StreamEventType.metadata,
            data={
                "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8}
            },
        )
        yield StreamEvent(type=StreamEventType.done, data={})


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _registry_with_mock() -> AsyncIterator[None]:
    """启动 registry + 注入 mock provider + mock-echo agent + mock embedding

    autouse + session-scoped：所有跨包 tests 共享。
    """
    init_registry()
    PROVIDERS["mock"] = _MockEchoProvider()
    AGENTS["mock-echo"] = AgentDef(
        key="mock-echo",
        provider="mock",
        description="mock echo agent for integration tests",
    )
    set_embedding_for_test(
        _DeterministicHashEmbedding(dim=1536, model="text-embedding-3-small")
    )
    yield
    set_embedding_for_test(None)


# ── Deterministic embedding（测试用，避免真实 OpenAI 调用） ──────


class _DeterministicHashEmbedding:
    """hash(text) 派生向量。同一文本必出同一向量。L2-normalized。

    用于：
    - knowledge ingest worker（确定性结果便于断言）
    - search 命中校验（用同文本 query 必能找回自己）
    """

    def __init__(self, *, dim: int, model: str) -> None:
        self.dim = dim
        self.model = model

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]

    def _vec(self, text: str) -> list[float]:
        # SHA256 → 32 bytes → 用作 PRNG 种子，铺到 dim 维
        seed = hashlib.sha256(text.encode("utf-8")).digest()
        out: list[float] = []
        i = 0
        while len(out) < self.dim:
            # 每 4 字节取一个 float（uniform on [-1, 1]）
            b = seed[i % 32 : (i % 32) + 4]
            if len(b) < 4:
                b = (b + seed)[:4]
            v = int.from_bytes(b, "big", signed=False)
            out.append((v / 0xFFFFFFFF) * 2 - 1)
            i += 1
            if i % 32 == 0:
                # 派生下一轮 seed 防止平坦
                seed = hashlib.sha256(seed).digest()
        # L2 normalize（让 cosine = 内积）
        norm = math.sqrt(sum(x * x for x in out)) or 1.0
        return [x / norm for x in out]


# ── HTTP client fixtures ────────────────────────────────


@pytest.fixture(scope="session", autouse=True)
def _init_crypto_jwt() -> None:
    """ASGITransport 不触发 FastAPI lifespan，测试期显式初始化"""
    init_crypto()
    init_jwt()


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as c:
        yield c


# ── 数据清理 ────────────────────────────────────────────


@pytest_asyncio.fixture(autouse=True)
async def _cleanup() -> AsyncIterator[None]:
    yield
    async with AsyncSessionLocal() as s:
        # 按外键依赖倒序清
        await s.execute(delete(Chunk))
        await s.execute(delete(Document))
        await s.execute(delete(KnowledgeBase).where(KnowledgeBase.kb_key.like("e2e-%")))
        await s.execute(delete(Task))
        await s.execute(delete(Message))
        await s.execute(delete(Conversation))
        await s.execute(delete(CallLog))
        await s.execute(delete(ApiKey).where(ApiKey.app_id.like("e2e-%")))
        # App 最后清（FK 被引）
        await s.execute(delete(App).where(App.app_key.like("e2e-%")))
        await s.commit()


# ── API key 工厂 ─────────────────────────────────────────


async def _ensure_app(s, app_key: str) -> None:
    """fixture 辅助：确保 apps 表里有对应 row（FK 前置）"""
    s.add(App(app_key=app_key, name=app_key))
    await s.flush()


@pytest_asyncio.fixture
async def admin_key() -> str:
    rand = secrets.token_hex(3)
    app_id = f"e2e-admin-{rand}"
    async with AsyncSessionLocal() as s:
        await _ensure_app(s, app_id)
        created = await create_api_key(
            s,
            CreateApiKeyRequest(
                app_id=app_id,
                name="e2e-admin",
                scopes=["admin"],
            ),
        )
        await s.commit()
    return created.plain_key


@pytest_asyncio.fixture
async def app_key() -> str:
    rand = secrets.token_hex(3)
    app_id = f"e2e-app-{rand}"
    async with AsyncSessionLocal() as s:
        await _ensure_app(s, app_id)
        created = await create_api_key(
            s,
            CreateApiKeyRequest(
                app_id=app_id,
                name="e2e-app",
                scopes=[],
            ),
        )
        await s.commit()
    return created.plain_key
