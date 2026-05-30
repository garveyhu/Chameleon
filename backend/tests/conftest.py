"""跨包集成测试 fixtures

- 注入 mock provider + agent 到 registry
- 注入 DeterministicHashEmbedding 替代真实 OpenAI 调用
- 强制跑在独立 test 库（见 _bootstrap_test_db），不碰 dev 数据
"""

# ruff: noqa: E402 —— 必须在 import chameleon 前设 DATABASE_URL 指向独立 test 库（#29）
from __future__ import annotations

import hashlib
import math
import secrets
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete


def _bootstrap_test_db() -> None:
    """强制 DATABASE_URL 指向独立 <db>_test 库，并建库 + 扩展 + alembic 迁移。

    conftest 的 _cleanup 等 fixture 会 delete(CallLog/User) 清表——必须隔离到
    test 库，否则清空 dev 运行数据（这是历史上"DB 被重置"的真因）。engine 在
    chameleon import 期绑定 URL，故本函数必须在任何 chameleon import 之前调用。
    可用 TEST_DATABASE_URL 覆盖（CI）。seed 由既有 _registry_with_mock fixture 跑。
    """
    import asyncio
    import json
    import os
    from pathlib import Path

    backend = Path(__file__).resolve().parents[1]
    db = json.loads((backend / "config" / "component.json").read_text())["database"]
    test_name = f"{db['db']}_test"
    test_url = os.environ.get("TEST_DATABASE_URL") or (
        f"postgresql+asyncpg://{db['user']}:{db['password']}"
        f"@{db['host']}:{db['port']}/{test_name}"
    )
    # 安全闸：库名必须含 _test，绝不在非 test 库上跑（防清 dev 数据）
    assert "_test" in test_url, f"拒绝在非 test 库跑测试: {test_url}"
    os.environ["DATABASE_URL"] = test_url

    async def _create_db_and_ext() -> None:
        import asyncpg

        base = f"{db['user']}:{db['password']}@{db['host']}:{db['port']}"
        admin = await asyncpg.connect(f"postgresql://{base}/postgres")
        try:
            if not await admin.fetchval(
                "select 1 from pg_database where datname=$1", test_name
            ):
                await admin.execute(f'create database "{test_name}"')
        finally:
            await admin.close()
        tconn = await asyncpg.connect(f"postgresql://{base}/{test_name}")
        try:
            await tconn.execute("create extension if not exists vector")
        finally:
            await tconn.close()

    asyncio.run(_create_db_and_ext())

    # alembic 跑在独立子进程：避免在 conftest import 期把 chameleon engine /
    # 事件循环带进测试进程（会引发 event-loop-closed 连接池级联）。
    import subprocess
    import sys

    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(backend),
        env={**os.environ, "DATABASE_URL": test_url},
        check=True,
        capture_output=True,
    )


_bootstrap_test_db()

from chameleon.app.main import create_app
from chameleon.integrations.embedding import set_for_test as set_embedding_for_test
from chameleon.data.infra.db import AsyncSessionLocal
from chameleon.data.infra.jwt import init_jwt
from chameleon.data.models import (
    ApiKey,
    CallLog,
    ChatSession,
    Chunk,
    Document,
    KnowledgeBase,
    Message,
    Task,
)
from chameleon.data.utils.crypto import init_crypto
from chameleon.providers.base import AGENTS, PROVIDERS, init_registry
from chameleon.providers.base.protocol import Provider
from chameleon.providers.base.types import (
    AgentDef,
    InvokeContext,
    StreamEvent,
    StreamEventType,
)
from chameleon.system.api_key.schemas import CreateApiKeyRequest
from chameleon.system.api_key.service import create_api_key

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
    # 让 seed 跑过让 agents 表有本地 agent 数据 → init_registry 能 load
    from chameleon.system.seed import run_seed_if_empty

    try:
        await run_seed_if_empty()
    except Exception:
        pass

    await init_registry()
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


@pytest_asyncio.fixture(autouse=True)
async def _reload_registry_each_test():
    """LLM cache + AGENTS/PROVIDERS dict 每个 test 前 reload 保稳

    每次 reset/init 后，需要重新注入 mock provider / mock-echo agent
    （session 级 _registry_with_mock 只在最开始注入一次，会被 reset 清掉）
    """
    from chameleon.integrations.llms.factory import reload_llm_cache
    from chameleon.providers.base import init_registry
    from chameleon.providers.base.registry import reset_registry_for_test

    try:
        await reload_llm_cache()
    except Exception:
        pass
    reset_registry_for_test()
    try:
        await init_registry()
    except Exception as e:
        from loguru import logger

        logger.warning("init_registry in test fixture failed: {}", e)
    # 重新注入 mock（被 reset 清掉了）
    PROVIDERS["mock"] = _MockEchoProvider()
    AGENTS["mock-echo"] = AgentDef(
        key="mock-echo",
        provider="mock",
        description="mock echo agent for integration tests",
    )
    yield


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
        await s.execute(delete(ChatSession))
        await s.execute(delete(CallLog))
        await s.execute(delete(ApiKey).where(ApiKey.app_id.like("e2e-%")))
        await s.commit()


# ── API key 工厂 ─────────────────────────────────────────


@pytest_asyncio.fixture
async def admin_key() -> str:
    rand = secrets.token_hex(3)
    app_id = f"e2e-admin-{rand}"
    async with AsyncSessionLocal() as s:
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
