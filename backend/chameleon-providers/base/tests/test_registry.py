"""Registry 构建逻辑单测（v0.2 DB-driven）

测 build_agent_registry_from_db / reload_agent_registry 与 DB agents 表交互。
"""

from __future__ import annotations

import secrets
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import delete

from chameleon.core.infra.db import AsyncSessionLocal
from chameleon.core.models import Agent
from chameleon.providers.base.protocol import Provider
from chameleon.providers.base.registry import (
    AGENTS,
    PROVIDERS,
    build_agent_registry_from_db,
    reload_agent_registry,
)
from chameleon.providers.base.types import InvokeContext, StreamEvent


class _FakeProvider(Provider):
    def __init__(self, name: str) -> None:
        self.name = name

    async def stream(self, ctx: InvokeContext) -> AsyncIterator[StreamEvent]:
        if False:
            yield StreamEvent(type="done", data={})  # noqa
        raise NotImplementedError


@pytest.fixture
async def cleanup_agents():
    yield
    async with AsyncSessionLocal() as s:
        await s.execute(delete(Agent).where(Agent.agent_key.like("registry-test-%")))
        await s.commit()


async def test_db_agent_loaded_when_enabled(cleanup_agents) -> None:
    """DB 里 enabled=True 的 external agent 被 build_agent_registry_from_db 加载"""
    key = f"registry-test-{secrets.token_hex(3)}"
    async with AsyncSessionLocal() as s:
        s.add(
            Agent(
                agent_key=key,
                name="t",
                source="dify",
                config={"endpoint": "https://x.example.com"},
                enabled=True,
            )
        )
        await s.commit()

    providers = {"dify": _FakeProvider("dify")}
    agents = await build_agent_registry_from_db(providers)
    assert key in agents
    assert agents[key].provider == "dify"
    assert agents[key].config["endpoint"] == "https://x.example.com"


async def test_db_agent_disabled_skipped(cleanup_agents) -> None:
    key = f"registry-test-{secrets.token_hex(3)}"
    async with AsyncSessionLocal() as s:
        s.add(
            Agent(
                agent_key=key,
                name="t",
                source="dify",
                enabled=False,
            )
        )
        await s.commit()

    providers = {"dify": _FakeProvider("dify")}
    agents = await build_agent_registry_from_db(providers)
    assert key not in agents


async def test_agent_with_unregistered_provider_skipped(cleanup_agents) -> None:
    key = f"registry-test-{secrets.token_hex(3)}"
    async with AsyncSessionLocal() as s:
        s.add(
            Agent(
                agent_key=key,
                name="t",
                source="unknown-provider",
                enabled=True,
            )
        )
        await s.commit()

    providers = {"dify": _FakeProvider("dify")}  # 没 unknown-provider
    agents = await build_agent_registry_from_db(providers)
    assert key not in agents


async def test_local_agent_requires_class_in_index(cleanup_agents) -> None:
    """DB 里 source='local' 但 class 不在 local_class_index → 跳过 + warn"""
    key = f"registry-test-{secrets.token_hex(3)}"
    async with AsyncSessionLocal() as s:
        s.add(
            Agent(
                agent_key=key,
                name="t",
                source="local",
                local_class_path="non.existent.Class",
                enabled=True,
            )
        )
        await s.commit()

    providers = {"local": _FakeProvider("local")}
    agents = await build_agent_registry_from_db(providers, local_class_index={})
    assert key not in agents


async def test_reload_agent_registry_picks_up_new_agent(cleanup_agents) -> None:
    """reload 后 AGENTS dict 出现新 agent

    本测试需要 init_registry 先跑过让 PROVIDERS 有 dify；
    单元测试隔离运行时 PROVIDERS 为空 → 直接 import provider 实例填充。
    """
    if "dify" not in PROVIDERS:
        from chameleon.providers.dify import PROVIDER as dify_provider

        PROVIDERS["dify"] = dify_provider

    key = f"registry-test-{secrets.token_hex(3)}"
    async with AsyncSessionLocal() as s:
        s.add(
            Agent(
                agent_key=key,
                name="t",
                source="dify",
                config={"endpoint": "https://x"},
                enabled=True,
            )
        )
        await s.commit()

    assert key not in AGENTS
    await reload_agent_registry()
    assert key in AGENTS
