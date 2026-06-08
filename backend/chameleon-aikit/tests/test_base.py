"""LLMRunner 执行层不变量（收口后所有内部 LLM 调用共享这套语义）。

红线：trace channel 归属正确（已有 scope 复用、无 scope 自开 internal）、重试与
fallback 容错行为。详见 docs/plans/2026-06-07-internal-llm-aikit.md §6/§10。
"""

from __future__ import annotations

import pytest

from chameleon.aikit import LLMRunner
from chameleon.aikit import base as aikit_base
from chameleon.core.observe.context import (
    TraceContext,
    current_trace_context,
    open_trace_scope,
)


class _FakeAI:
    def __init__(self, text: str) -> None:
        self.content = text


class _FakeClient:
    """记录调用时所处的 trace channel；可按脚本前若干次抛错以测重试。"""

    def __init__(self, *, text: str = "ok", fail_times: int = 0) -> None:
        self._text = text
        self._fail_times = fail_times
        self.calls = 0
        self.seen_channel: str | None = None

    async def ainvoke(self, messages):  # noqa: ANN001
        self.calls += 1
        ctx = current_trace_context()
        self.seen_channel = ctx.channel if ctx else None
        if self.calls <= self._fail_times:
            raise RuntimeError("boom")
        return _FakeAI(self._text)


@pytest.fixture
def patch_factory(monkeypatch):
    """把 LLMFactory.create 替换成返回指定桩 client。"""

    def _install(client: _FakeClient) -> _FakeClient:
        monkeypatch.setattr(
            aikit_base.LLMFactory, "create", lambda name=None: client
        )
        return client

    return _install


async def test_reuses_existing_scope_without_overriding(patch_factory):
    client = patch_factory(_FakeClient(text="judged"))
    async with open_trace_scope(TraceContext(request_id="r1", channel="eval")):
        out = await LLMRunner.run_text("judge this", model="m", retries=0)
        assert out == "judged"
        assert client.seen_channel == "eval"  # 复用 eval，未覆盖成 internal
        assert current_trace_context().channel == "eval"  # scope 未被破坏


async def test_opens_internal_scope_when_bare(patch_factory):
    client = patch_factory(_FakeClient())
    assert current_trace_context() is None
    await LLMRunner.run_text("classify this", model="m", retries=0)
    assert client.seen_channel == "internal"
    assert current_trace_context() is None  # 退出后复位


async def test_retry_then_succeed(patch_factory):
    client = patch_factory(_FakeClient(text="recovered", fail_times=1))
    out = await LLMRunner.run_text("x", retries=1)
    assert out == "recovered"
    assert client.calls == 2


async def test_fallback_when_exhausted(patch_factory):
    client = patch_factory(_FakeClient(fail_times=99))
    out = await LLMRunner.run_text("x", retries=1, fallback="FB")
    assert out == "FB"
    assert client.calls == 2  # retries+1 次尝试


async def test_raises_when_no_fallback(patch_factory):
    patch_factory(_FakeClient(fail_times=99))
    with pytest.raises(RuntimeError):
        await LLMRunner.run_text("x", retries=0)


async def test_run_stream_yields_deltas(patch_factory):
    class _StreamClient:
        seen_channel: str | None = None

        async def astream(self, messages):  # noqa: ANN001
            self._c = current_trace_context()
            _StreamClient.seen_channel = self._c.channel if self._c else None
            for piece in ("hel", "lo"):
                yield _FakeAI(piece)

    import chameleon.aikit.base as b

    sc = _StreamClient()
    b.LLMFactory.create = lambda name=None: sc  # type: ignore[assignment]
    out = "".join([d async for d in LLMRunner.run_stream("x")])
    assert out == "hello"
    assert _StreamClient.seen_channel == "internal"
