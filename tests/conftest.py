"""跨包集成测试 fixtures

注入一个 mock provider + agent 到 registry，方便测试整条 invoke 流程。
"""

from __future__ import annotations

import secrets
from collections.abc import AsyncIterator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from chameleon.app.main import create_app
from chameleon.app.modules.api_key.schemas import CreateApiKeyRequest
from chameleon.app.modules.api_key.service import create_api_key
from chameleon.core.db import AsyncSessionLocal
from chameleon.core.models import ApiKey, CallLog, Conversation, Message
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
    """启动 registry + 注入 mock provider + mock-echo agent

    autouse + session-scoped：所有跨包 tests 共享一个 registry。
    """
    init_registry()
    PROVIDERS["mock"] = _MockEchoProvider()
    AGENTS["mock-echo"] = AgentDef(
        key="mock-echo",
        provider="mock",
        description="mock echo agent for integration tests",
    )
    yield


# ── HTTP client fixtures ────────────────────────────────


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
        await s.execute(delete(Message))
        await s.execute(delete(Conversation))
        await s.execute(delete(CallLog))
        await s.execute(delete(ApiKey).where(ApiKey.app_id.like("e2e-%")))
        await s.commit()


# ── API key 工厂 ─────────────────────────────────────────


@pytest_asyncio.fixture
async def admin_key() -> str:
    rand = secrets.token_hex(3)
    async with AsyncSessionLocal() as s:
        created = await create_api_key(
            s,
            CreateApiKeyRequest(
                app_id=f"e2e-admin-{rand}",
                name="e2e-admin",
                scopes=["admin"],
            ),
        )
        await s.commit()
    return created.plain_key


@pytest_asyncio.fixture
async def app_key() -> str:
    rand = secrets.token_hex(3)
    async with AsyncSessionLocal() as s:
        created = await create_api_key(
            s,
            CreateApiKeyRequest(
                app_id=f"e2e-app-{rand}",
                name="e2e-app",
                scopes=[],
            ),
        )
        await s.commit()
    return created.plain_key
