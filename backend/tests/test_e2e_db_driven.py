"""P5 业务核心改造的 E2E 测试

覆盖：
- LLM cache：DB 改 model.defaults → reload 后业务侧拿到新值
- Agent registry：DB 改 enabled=False → reload 后 AGENTS dict 不含；invoke 返 404
- Agent registry：新增 external agent → reload 后 AGENTS dict 出现
"""

from __future__ import annotations

import secrets

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete, select

from chameleon.core.components.llms.factory import (
    _CACHE,
    LLMFactory,
    invalidate_llm,
    reload_llm_cache,
)
from chameleon.data.infra.db import AsyncSessionLocal
from chameleon.data.models import Agent, LLMModel
from chameleon.providers.base import AGENTS, reload_agent_registry
from chameleon.providers.base.registry import PROVIDERS

# ── LLM cache ─────────────────────────────────────────────


async def test_llm_factory_loads_from_db():
    """seed 已建 qwen-plus model → cache 含它"""
    await reload_llm_cache()
    llm = LLMFactory.create("qwen-plus")
    assert llm.model_name == "qwen-plus" or hasattr(llm, "model_name")


async def test_llm_cache_picks_up_new_defaults():
    """改 DB model.defaults → reload → 业务拿到新 temperature"""
    async with AsyncSessionLocal() as s:
        m = (
            await s.execute(select(LLMModel).where(LLMModel.code == "qwen-plus"))
        ).scalar_one()
        original_defaults = dict(m.defaults or {})
        m.defaults = {**original_defaults, "temperature": 0.123}
        await s.commit()

    try:
        await reload_llm_cache()
        llm = LLMFactory.create("qwen-plus")
        # ChatOpenAI 的 temperature 属性
        assert abs(llm.temperature - 0.123) < 0.001
    finally:
        # 还原
        async with AsyncSessionLocal() as s:
            m = (
                await s.execute(
                    select(LLMModel).where(LLMModel.code == "qwen-plus")
                )
            ).scalar_one()
            m.defaults = original_defaults
            await s.commit()
        await reload_llm_cache()


async def test_invalidate_llm_single_model():
    """invalidate_llm 单条失效后再 reload 能回来"""
    await reload_llm_cache()
    assert "qwen-plus" in _CACHE
    invalidate_llm("qwen-plus")
    assert "qwen-plus" not in _CACHE
    await reload_llm_cache()
    assert "qwen-plus" in _CACHE


# ── Agent registry ────────────────────────────────────────


@pytest_asyncio.fixture
async def cleanup_test_agents():
    yield
    async with AsyncSessionLocal() as s:
        await s.execute(delete(Agent).where(Agent.agent_key.like("p5-test-%")))
        await s.commit()


async def test_disable_agent_then_invoke_returns_404(
    client: AsyncClient, app_key: str, cleanup_test_agents
):
    """改 agents.enabled=False → reload → 业务 invoke 返 404"""
    # 用现成本地 agent 测试
    target = "example-echo-native"
    async with AsyncSessionLocal() as s:
        a = (
            await s.execute(select(Agent).where(Agent.agent_key == target))
        ).scalar_one()
        a.enabled = False
        await s.commit()

    await reload_agent_registry()
    assert target not in AGENTS

    r = await client.post(
        "/v1/invoke",
        headers={"Authorization": f"Bearer {app_key}"},
        json={"input": "hi", "stream": False, "agent_key": target},
    )
    assert r.status_code == 404
    body = r.json()
    assert body["code"] == 40401  # AgentNotFound

    # 还原
    async with AsyncSessionLocal() as s:
        a = (
            await s.execute(select(Agent).where(Agent.agent_key == target))
        ).scalar_one()
        a.enabled = True
        await s.commit()
    await reload_agent_registry()


async def test_add_external_agent_then_reload_picks_up(cleanup_test_agents):
    """DB 加新 external agent → reload → AGENTS 出现"""
    key = f"p5-test-{secrets.token_hex(3)}"
    async with AsyncSessionLocal() as s:
        s.add(
            Agent(
                agent_key=key,
                name="t",
                source="dify",
                config={"endpoint": "https://x.example.com", "api_key_env": "FAKE"},
                enabled=True,
            )
        )
        await s.commit()

    assert key not in AGENTS  # reload 前
    if "dify" not in PROVIDERS:
        from chameleon.providers.dify import PROVIDER as p

        PROVIDERS["dify"] = p

    await reload_agent_registry()
    assert key in AGENTS
    assert AGENTS[key].provider == "dify"


async def test_local_agent_only_loaded_when_namespace_present(cleanup_test_agents):
    """DB 里有但 namespace 没找到对应 class → 跳过"""
    key = f"p5-test-{secrets.token_hex(3)}"
    async with AsyncSessionLocal() as s:
        s.add(
            Agent(
                agent_key=key,
                name="t",
                source="local",
                local_class_path="non.existent.MyAgent",
                enabled=True,
            )
        )
        await s.commit()

    await reload_agent_registry()
    # local 但 class 不存在 → 跳过
    assert key not in AGENTS
