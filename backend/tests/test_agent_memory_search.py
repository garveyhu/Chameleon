"""agentkit 语义记忆 hybrid 召回真库往返（T1-1 memory 升级 M1）。

真 test-DB（pgvector + content_tsv GENERATED，走 alembic 迁移），embedding 用 conftest
注入的 DeterministicHashEmbedding（同文本同向量；非语义，故断言靠 BM25 词项 + scope
结构隔离 + 删除物理消失这类鲁棒信号，不依赖 hash 向量的"语义"近邻）。

验：① set 旁路索引 → search 命中并回填原始值；② scope 隔离（A 搜不到 B）；
③ 更新覆盖索引文本/值；④ 删除（set None）同步删向量行。
不 mock DB —— InProcessTransport.memory_set/search 与 engine 索引/召回打同一 test 库。
"""

from __future__ import annotations

import pytest
from sqlalchemy import delete, select

from chameleon.data.infra.db import AsyncSessionLocal
from chameleon.data.models import AgentMemory, AgentMemoryVector
from chameleon.engine.retrieval.memory_pipeline import wire_memory_vector_bridge
from chameleon.providers.local.agentkit_runner import InProcessTransport

_AGENT = "_t_mem_search"


async def _clean() -> None:
    async with AsyncSessionLocal() as s:
        await s.execute(
            delete(AgentMemoryVector).where(AgentMemoryVector.agent_key == _AGENT)
        )
        await s.execute(delete(AgentMemory).where(AgentMemory.agent_key == _AGENT))
        await s.commit()


def _transport(scope: str) -> InProcessTransport:
    return InProcessTransport(agent_key=_AGENT, bindings={}, slots={}, scope_ref=scope)


@pytest.mark.asyncio
async def test_memory_search_roundtrip_and_scope_isolation() -> None:
    wire_memory_vector_bridge()
    await _clean()
    a = _transport("user-A")
    b = _transport("user-B")
    await a.memory_set("fav_lang", "用户最喜欢的编程语言是 Python")
    await a.memory_set("city", "用户住在北京")
    await b.memory_set("fav_lang", "用户最喜欢的编程语言是 Rust")

    # ① BM25 词项召回命中 fav_lang，并从 KV 真相源回填原始值
    hits = await a.memory_search("编程语言", top_k=5)
    fav = next((h for h in hits if h.key == "fav_lang"), None)
    assert fav is not None, "scope A 应召回 fav_lang"
    assert fav.value == "用户最喜欢的编程语言是 Python", "原始值应从 AgentMemory 回填"
    assert fav.score > 0
    assert fav.text == "用户最喜欢的编程语言是 Python"

    # ② scope 隔离：A 的召回绝不含 B（Rust）；B 的召回绝不含 A（Python）
    assert all("Rust" not in (h.text or "") for h in hits), "A 串到了 B 的记忆"
    b_hits = await b.memory_search("编程语言", top_k=5)
    assert any("Rust" in (h.text or "") for h in b_hits)
    assert all("Python" not in (h.text or "") for h in b_hits), "B 串到了 A 的记忆"

    await _clean()


@pytest.mark.asyncio
async def test_memory_update_overwrites_and_delete_removes_vector() -> None:
    wire_memory_vector_bridge()
    await _clean()
    a = _transport("user-C")
    await a.memory_set("note", "喜欢苹果")

    # ③ 更新覆盖索引文本 + 值（不依赖 hash 向量语义，直接看回显文本/值）
    await a.memory_set("note", "喜欢香蕉")
    hits = await a.memory_search("香蕉", top_k=5)
    note = next((h for h in hits if h.key == "note"), None)
    assert note is not None
    assert note.text == "喜欢香蕉" and note.value == "喜欢香蕉", "更新应覆盖索引文本与值"

    async with AsyncSessionLocal() as s:
        row = (
            await s.execute(
                select(AgentMemoryVector).where(
                    AgentMemoryVector.agent_key == _AGENT,
                    AgentMemoryVector.scope_ref == "user-C",
                    AgentMemoryVector.mkey == "note",
                )
            )
        ).scalar_one_or_none()
    assert row is not None and row.text == "喜欢香蕉", "向量行应反映更新"

    # ④ 删除（set None）→ 向量行物理删除，search 不再返回（行没了，两路都召不回）
    await a.memory_set("note", None)
    hits2 = await a.memory_search("香蕉", top_k=5)
    assert all(h.key != "note" for h in hits2), "删除后不应再召回"
    async with AsyncSessionLocal() as s:
        row2 = (
            await s.execute(
                select(AgentMemoryVector).where(
                    AgentMemoryVector.agent_key == _AGENT,
                    AgentMemoryVector.mkey == "note",
                )
            )
        ).scalar_one_or_none()
    assert row2 is None, "set(None) 应同步删除向量行"

    await _clean()


@pytest.mark.asyncio
async def test_reserved_keys_excluded_from_search() -> None:
    """框架保留键（__chm_*__：journal/checkpoint/working）不入语义召回集。"""
    wire_memory_vector_bridge()
    await _clean()
    a = _transport("user-D")
    await a.memory_set("__chm_checkpoint__", {"step": "中间状态 香蕉"})
    await a.memory_set("real", "真实记忆 香蕉")
    # 经 _MemoryProxy.search（带保留键过滤）；这里直接验 transport 层也不索引保留键
    async with AsyncSessionLocal() as s:
        rows = (
            await s.execute(
                select(AgentMemoryVector).where(AgentMemoryVector.agent_key == _AGENT)
            )
        ).scalars().all()
    keys = {r.mkey for r in rows}
    assert "__chm_checkpoint__" not in keys, "保留键不应被向量索引"
    assert "real" in keys
    await _clean()
