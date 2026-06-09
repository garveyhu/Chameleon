"""T3-1 eval 闭环：agentkit @agent 当被测对象跑数据集回归打分（真 test-DB）。

发现：eval runner 的 agent 路径（_invoke_via_agent → PROVIDERS[provider].invoke）provider
无关——agentkit @agent 是 provider='local' 的 agent，**已能**经 DatasetRunRequest.agent_key 当
被测对象，无需新 source 分支。本测把这条闭环钉成回归网：注册真 @agent → run_dataset(agent_key=)
→ 经统一 invoke 聚合 answer → judge 打分。

不 mock DB；agentkit 内部 ctx.complete 的 chat_model 用 Fake（不打真 LLM）。
"""

from __future__ import annotations

import sys
import types

import pytest
from sqlalchemy import delete

from chameleon.agentkit import AgentRun, ModelSlot, agent
from chameleon.data.infra.db import AsyncSessionLocal
from chameleon.data.models import Dataset, DatasetItem, DatasetRun, DatasetRunItem
from chameleon.providers.base.registry import AGENTS
from chameleon.providers.base.types import AgentDef
from chameleon.providers.local.agentkit_runner import InProcessTransport
from chameleon.system.datasets.runner import run_dataset

_KEY = "_t_eval_agentkit"
_MOD = "chameleon._test_eval_agentkit.agent"
_ANSWER = "PONG-eval-42"


class _FakeChat:
    def bind_tools(self, schemas):  # noqa: ANN001
        return self

    async def ainvoke(self, messages, **kw):  # noqa: ANN001
        class _M:
            content = _ANSWER
            tool_calls: list = []
            usage_metadata = {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2}

        return _M()


def _register_agentkit_agent() -> None:
    if _MOD not in sys.modules:

        @agent(key=_KEY, name="eval 闭环测试", models=[ModelSlot("chat", "c")])
        async def handle(ctx: AgentRun):
            # 回固定答案（与数据集 expected 对齐，让 contains judge 命中）
            yield await ctx.complete(user=ctx.query)

        m = types.ModuleType(_MOD)
        m.handle = handle  # type: ignore[attr-defined]
        handle.__module__ = _MOD
        sys.modules[_MOD] = m
    # 注册进 AGENTS（provider='local' + agentkit 定位标记），让 _invoke_via_agent 找到
    AGENTS[_KEY] = AgentDef(
        key=_KEY,
        provider="local",
        description="eval 闭环测试 agent",
        config={"__agentkit_module__": _MOD, "__agentkit_attr__": "handle"},
    )


@pytest.mark.asyncio
async def test_agentkit_agent_as_eval_subject(monkeypatch) -> None:
    monkeypatch.setattr(
        InProcessTransport, "chat_model",
        lambda self, *, slot=None, model=None: _FakeChat(),
    )
    _register_agentkit_agent()

    async with AsyncSessionLocal() as s:
        ds = Dataset(name=f"eval-akit-{_KEY}")
        s.add(ds)
        await s.flush()
        for i in range(2):
            s.add(
                DatasetItem(
                    dataset_id=ds.id,
                    input_payload={"user_input": f"ping #{i}"},
                    expected_output={"answer": _ANSWER},
                )
            )
        await s.commit()
        dataset_id = ds.id

    try:
        async with AsyncSessionLocal() as s:
            run = await run_dataset(
                s,
                dataset_id=dataset_id,
                name="agentkit-eval-run",
                judge="contains",
                agent_key=_KEY,
            )
            run_id = run.id
            assert run.agent_key == _KEY
            assert run.status == "success", f"agentkit eval run 应成功: {run.summary}"
            assert run.summary["mean_score"] == 1.0, "agent 答案应 contains-命中 expected"
            assert run.summary["ok"] == 2 and run.summary["fail"] == 0

        # 逐 item 落库验证：actual_output 来自 agentkit 聚合 answer，score=1.0
        async with AsyncSessionLocal() as s:
            from sqlalchemy import select

            items = (
                await s.execute(
                    select(DatasetRunItem).where(DatasetRunItem.dataset_run_id == run_id)
                )
            ).scalars().all()
        assert len(items) == 2
        for ri in items:
            assert ri.score == 1.0
            assert _ANSWER in str(ri.actual_output), "被测 agent 的 answer 应落进 run item"
    finally:
        async with AsyncSessionLocal() as s:
            await s.execute(delete(DatasetRunItem).where(DatasetRunItem.dataset_run_id == run_id))
            await s.execute(delete(DatasetRun).where(DatasetRun.dataset_id == dataset_id))
            await s.execute(delete(DatasetItem).where(DatasetItem.dataset_id == dataset_id))
            await s.execute(delete(Dataset).where(Dataset.id == dataset_id))
            await s.commit()
        AGENTS.pop(_KEY, None)
