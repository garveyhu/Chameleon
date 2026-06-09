"""身份/作用域演示（真 test-DB）：记忆如何标识「一个用户 / 一段对话」。

scope_ref = end_user_id（用户，跨会话）优先，退化 session_id（对话）。本演示证明：
  · 同一 end_user 跨**不同 session**仍共享记忆（记忆跟着「人」走，不是跟着「这次对话」走）
  · 不同 end_user **互相隔离**（alice 存的，bob 绝对搜不到）
这就是「怎么标识一个用户」的活证明。运行：pytest -s tests/test_identity_scoping_demo.py
"""

from __future__ import annotations

import pytest
from sqlalchemy import delete

from chameleon.agentkit import AgentRun
from chameleon.data.infra.db import AsyncSessionLocal
from chameleon.data.models import AgentMemory, AgentMemoryVector
from chameleon.engine.retrieval.memory_pipeline import wire_memory_vector_bridge
from chameleon.providers.local.agentkit_runner import InProcessTransport

_AGENT = "advisor-demo"  # 演示用我们刚建的那个 agent 的 key


def _run(*, end_user: str, session: str) -> AgentRun:
    """构造一次运行的 ctx —— scope_ref 取 end_user（跨会话），session 只是这次对话标识。"""
    t = InProcessTransport(agent_key=_AGENT, bindings={}, slots={}, scope_ref=end_user)
    return AgentRun(
        transport=t, agent_key=_AGENT, query="q", messages=[], history=[],
        session_id=session, config={},
    )


async def _clean() -> None:
    async with AsyncSessionLocal() as s:
        await s.execute(delete(AgentMemoryVector).where(AgentMemoryVector.agent_key == _AGENT))
        await s.execute(delete(AgentMemory).where(AgentMemory.agent_key == _AGENT))
        await s.commit()


@pytest.mark.asyncio
async def test_memory_follows_the_user_across_sessions_and_isolates_users() -> None:
    wire_memory_vector_bridge()
    await _clean()

    # alice 在「会话1」告诉 agent 一个偏好
    await _run(end_user="user:alice", session="conv-A1").memory.set(
        "pref", "alice 最喜欢的编程语言是 Python"
    )
    # bob 在他自己的会话告诉 agent 另一个偏好
    await _run(end_user="user:bob", session="conv-B1").memory.set(
        "pref", "bob 最喜欢的编程语言是 Rust"
    )

    # ① 同一用户跨「会话2」（全新对话）—— 仍能召回（记忆跟着「人」走）
    alice_later = _run(end_user="user:alice", session="conv-A2-全新对话")
    hits = await alice_later.memory.search("编程语言", top_k=5)
    alice_recall = [h.text for h in hits]
    print("\n【alice 在全新对话里搜“编程语言”】→", alice_recall)
    assert any("Python" in t for t in alice_recall), "同一 end_user 跨会话应能召回"

    # ② 跨用户隔离 —— alice 绝对搜不到 bob 的
    assert all("Rust" not in t for t in alice_recall), "alice 不该看到 bob 的记忆"

    bob = _run(end_user="user:bob", session="conv-B2")
    bob_recall = [h.text for h in await bob.memory.search("编程语言", top_k=5)]
    print("【bob   在自己对话里搜“编程语言”】→", bob_recall)
    assert any("Rust" in t for t in bob_recall)
    assert all("Python" not in t for t in bob_recall), "bob 不该看到 alice 的记忆"

    print("\n结论：scope_ref=end_user_id 时记忆按『人』跨会话共享；无身份时退化按『对话』session 隔离。")
    await _clean()
