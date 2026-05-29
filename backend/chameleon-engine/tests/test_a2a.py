"""P20.4 PR #55 单元测试：A2A 协议 + AgentRunner 红线与 trace 嵌套"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest

from chameleon.core.api.exceptions import (
    AgentNotFoundError,
    BusinessError,
    ResultCode,
)
from chameleon.core.observe.context import current_observation_id
from chameleon.engine.agent import (
    MAX_DEPTH,
    A2ACallSpec,
    A2AResult,
    AgentRunner,
    call_agent,
)
from chameleon.providers.base import (
    AGENTS,
    PROVIDERS,
    AgentDef,
    InvokeContext,
    InvokeResult,
    Provider,
    StreamEvent,
    StreamEventType,
    Usage,
)
from chameleon.providers.base.types import _StreamAggregator  # noqa: F401

# ── stub provider 和 agent ──────────────────────────────


class _StubProvider(Provider):
    """记录 parent_id + 透传可控输出的 fake provider"""

    name = "stub"

    def __init__(self) -> None:
        self.invocations: list[dict[str, Any]] = []
        self.answer_text: str = "stub-answer"
        self.usage_total: int = 100
        # 嵌套调用 hook
        self.nested_call_spec: A2ACallSpec | None = None
        self.captured_parent_ids: list[str | None] = []

    async def stream(self, ctx: InvokeContext) -> AsyncIterator[StreamEvent]:
        # 不实现真正的 stream；invoke() 直接 override
        if False:
            yield StreamEvent(type=StreamEventType.delta)

    async def invoke(self, ctx: InvokeContext) -> InvokeResult:
        self.captured_parent_ids.append(current_observation_id())
        self.invocations.append(
            {"agent": ctx.agent_def.key, "request_id": ctx.request_id}
        )
        # 嵌套：在 stub 内部再做一次 A2A 调用，验证 observation 嵌套
        if self.nested_call_spec is not None:
            spec = self.nested_call_spec
            self.nested_call_spec = None  # 单次触发
            await AgentRunner.call_agent(spec)
        return InvokeResult(
            answer=self.answer_text,
            session_id=ctx.session_id,
            request_id=ctx.request_id,
            usage=Usage(
                prompt_tokens=10,
                completion_tokens=self.usage_total - 10,
                total_tokens=self.usage_total,
            ),
        )


@pytest.fixture
def stub_setup():
    """临时注册 stub provider + 2 个 stub agents，测试结束清理"""
    p = _StubProvider()
    PROVIDERS["stub"] = p
    AGENTS["a2a-alpha"] = AgentDef(
        key="a2a-alpha", provider="stub", description="alpha stub"
    )
    AGENTS["a2a-beta"] = AgentDef(
        key="a2a-beta", provider="stub", description="beta stub"
    )
    try:
        yield p
    finally:
        PROVIDERS.pop("stub", None)
        AGENTS.pop("a2a-alpha", None)
        AGENTS.pop("a2a-beta", None)


# ── 红线校验 ────────────────────────────────────────────


async def test_call_agent_without_trace_id_rejected(stub_setup: _StubProvider):
    with pytest.raises(BusinessError) as exc:
        await call_agent(
            source="caller",
            target="a2a-alpha",
            input="hi",
            trace_id="",  # 红线：空 trace_id 必须拒绝
            budget_remaining=1000,
        )
    assert exc.value.code == ResultCode.ValidationError


async def test_call_agent_with_zero_budget_rejected(stub_setup: _StubProvider):
    with pytest.raises(BusinessError) as exc:
        await call_agent(
            source="caller",
            target="a2a-alpha",
            input="hi",
            trace_id="tid-1",
            budget_remaining=0,
        )
    assert exc.value.code == ResultCode.ValidationError


async def test_call_agent_with_negative_budget_rejected(stub_setup: _StubProvider):
    with pytest.raises(BusinessError) as exc:
        await call_agent(
            source="caller",
            target="a2a-alpha",
            input="hi",
            trace_id="tid-1",
            budget_remaining=-5,
        )
    assert exc.value.code == ResultCode.ValidationError


async def test_call_agent_depth_at_max_rejected(stub_setup: _StubProvider):
    with pytest.raises(BusinessError) as exc:
        await call_agent(
            source="caller",
            target="a2a-alpha",
            input="hi",
            trace_id="tid-1",
            budget_remaining=1000,
            depth=MAX_DEPTH,
        )
    assert exc.value.code == ResultCode.ValidationError


async def test_call_agent_target_not_in_registry(stub_setup: _StubProvider):
    with pytest.raises(AgentNotFoundError):
        await call_agent(
            source="caller",
            target="not-registered",
            input="hi",
            trace_id="tid-1",
            budget_remaining=1000,
        )


# ── happy path + budget 扣减 ────────────────────────────


async def test_call_agent_success_deducts_budget(stub_setup: _StubProvider):
    stub_setup.usage_total = 250
    res = await call_agent(
        source="caller",
        target="a2a-alpha",
        input="hello",
        trace_id="tid-success",
        budget_remaining=1000,
    )
    assert isinstance(res, A2AResult)
    assert res.result.answer == "stub-answer"
    assert res.budget_consumed == 250
    assert res.budget_remaining == 750
    assert res.sub_observation_id  # 非空


async def test_call_agent_budget_floor_at_zero(stub_setup: _StubProvider):
    """消耗超预算时 budget_remaining 不为负"""
    stub_setup.usage_total = 5000
    res = await call_agent(
        source="caller",
        target="a2a-alpha",
        input="hi",
        trace_id="tid-overflow",
        budget_remaining=100,
    )
    assert res.budget_remaining == 0
    assert res.budget_consumed == 5000


async def test_call_agent_propagates_trace_id_as_request_id(
    stub_setup: _StubProvider,
):
    await call_agent(
        source="caller",
        target="a2a-alpha",
        input="hi",
        trace_id="my-trace-xyz",
        budget_remaining=1000,
    )
    assert len(stub_setup.invocations) == 1
    assert stub_setup.invocations[0]["request_id"] == "my-trace-xyz"


# ── observation 嵌套验证 ──────────────────────────────


async def test_nested_call_inherits_parent_observation(
    stub_setup: _StubProvider,
):
    """alpha 调 beta：在 beta 的 provider.invoke 里能拿到 alpha 的 observation id"""
    nested_spec = A2ACallSpec(
        source_agent_key="a2a-alpha",
        target_agent_key="a2a-beta",
        input="from alpha",
        trace_id="tid-nested",
        budget_remaining=500,
        depth=1,
    )
    stub_setup.nested_call_spec = nested_spec

    await call_agent(
        source="caller",
        target="a2a-alpha",
        input="start",
        trace_id="tid-nested",
        budget_remaining=1000,
    )
    # 两次 invoke：alpha + beta
    assert len(stub_setup.captured_parent_ids) == 2
    # alpha 跑时 parent_id 是 outer observe（非 None）
    outer_obs = stub_setup.captured_parent_ids[0]
    # beta 跑时 parent_id 是 alpha 的 observe（也非 None，且不等于 outer）
    inner_obs = stub_setup.captured_parent_ids[1]
    assert outer_obs is not None
    assert inner_obs is not None
    assert outer_obs != inner_obs


async def test_nested_call_at_max_depth_rejected(stub_setup: _StubProvider):
    """alpha (depth=MAX_DEPTH-1) 还能调；再深一层（=MAX_DEPTH）被拒"""
    # depth=MAX_DEPTH 直接拒绝
    with pytest.raises(BusinessError):
        await AgentRunner.call_agent(
            A2ACallSpec(
                source_agent_key="alpha",
                target_agent_key="a2a-beta",
                input="x",
                trace_id="tid",
                budget_remaining=100,
                depth=MAX_DEPTH,
            )
        )
