"""ctx 弹性 / 瞬时退避重试（T2-2）—— 离线、确定性单测（无 DB / 无真 LLM）。

验：① 瞬时错误分类器（rate limit/timeout/5xx/连接 → 重试；4xx/校验/解析 → 不重试）；
② ctx.complete 瞬时错误退避重试至成功；③ 非瞬时立刻抛、不空转；④ retries=0 不重试；
⑤ run_with_tools（InProcessTransport.run_tool_loop）每步 ainvoke 同样瞬时重试。
"""

from __future__ import annotations

import pytest

import chameleon.agentkit._runtime as rt
from chameleon.agentkit import AgentRun
from chameleon.agentkit._runtime import _is_transient_error, _retry_transient
from chameleon.agentkit.testing import FakeTransport


class _RateLimit(Exception):
    pass


class _Validation(Exception):
    pass


class _Status503(Exception):
    status_code = 503


def test_is_transient_error_classification() -> None:
    assert _is_transient_error(_RateLimit())  # 类名含 ratelimit
    assert _is_transient_error(_Status503())  # status_code=503
    assert _is_transient_error(TimeoutError())
    assert _is_transient_error(ConnectionError())
    assert not _is_transient_error(_Validation())  # 非瞬时
    assert not _is_transient_error(ValueError("bad schema"))  # 解析/校验类


@pytest.mark.asyncio
async def test_retry_transient_exhausts_then_raises(monkeypatch) -> None:
    monkeypatch.setattr(rt, "_RETRY_BASE_DELAY", 0)
    calls = {"n": 0}

    async def always():
        calls["n"] += 1
        raise _RateLimit("429")

    with pytest.raises(_RateLimit):
        await _retry_transient(always, retries=2)
    assert calls["n"] == 3  # 1 初次 + 2 重试


class _FlakyChat:
    """ainvoke 前 fail_times 次抛瞬时错误，之后返固定内容。"""

    def __init__(self, fail_times: int, exc: Exception) -> None:
        self.fail_times = fail_times
        self.exc = exc
        self.calls = 0

    def bind_tools(self, schemas):  # noqa: ANN001
        return self

    async def ainvoke(self, messages, **kw):  # noqa: ANN001
        self.calls += 1
        if self.calls <= self.fail_times:
            raise self.exc

        class _M:
            content = "RECOVERED"
            tool_calls: list = []
            usage_metadata = {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2}

        return _M()


class _FlakyTransport(FakeTransport):
    """复用 FakeTransport，仅把 chat_model 换成 flaky chat（注瞬时错误）。"""

    def __init__(self, chat) -> None:  # noqa: ANN001
        super().__init__()
        self._flaky = chat

    def chat_model(self, *, slot=None, model=None):  # noqa: ANN001, ANN201
        return self._flaky


@pytest.mark.asyncio
async def test_complete_retries_transient_then_succeeds(monkeypatch) -> None:
    monkeypatch.setattr(rt, "_RETRY_BASE_DELAY", 0)
    chat = _FlakyChat(fail_times=2, exc=_RateLimit("429"))
    run = AgentRun(
        transport=_FlakyTransport(chat), agent_key="x", query="q", messages=[],
        history=[], session_id=None, config={}, retries=3,
    )
    out = await run.complete(user="hi")
    assert out == "RECOVERED"
    assert chat.calls == 3  # 2 瞬时失败 + 1 成功


@pytest.mark.asyncio
async def test_complete_does_not_retry_non_transient(monkeypatch) -> None:
    monkeypatch.setattr(rt, "_RETRY_BASE_DELAY", 0)
    chat = _FlakyChat(fail_times=99, exc=_Validation("bad"))
    run = AgentRun(
        transport=_FlakyTransport(chat), agent_key="x", query="q", messages=[],
        history=[], session_id=None, config={}, retries=3,
    )
    with pytest.raises(_Validation):
        await run.complete(user="hi")
    assert chat.calls == 1  # 非瞬时：只调一次，不重试


@pytest.mark.asyncio
async def test_complete_retries_zero_no_retry(monkeypatch) -> None:
    monkeypatch.setattr(rt, "_RETRY_BASE_DELAY", 0)
    chat = _FlakyChat(fail_times=1, exc=_RateLimit("429"))
    run = AgentRun(
        transport=_FlakyTransport(chat), agent_key="x", query="q", messages=[],
        history=[], session_id=None, config={}, retries=0,
    )
    with pytest.raises(_RateLimit):
        await run.complete(user="hi")
    assert chat.calls == 1  # retries=0：瞬时也不重试


@pytest.mark.asyncio
async def test_run_tool_loop_retries_transient_per_step(monkeypatch) -> None:
    """InProcessTransport.run_tool_loop 每步 ainvoke 瞬时退避重试（无 DB：直接驱动 transport）。"""
    monkeypatch.setattr(rt, "_RETRY_BASE_DELAY", 0)
    from chameleon.providers.local.agentkit_runner import InProcessTransport

    chat = _FlakyChat(fail_times=2, exc=_Status503())
    t = InProcessTransport(agent_key="x", bindings={}, slots={}, retries=3)
    monkeypatch.setattr(t, "chat_model", lambda *, slot=None, model=None: chat)

    out = "".join(
        [
            delta
            async for delta in t.run_tool_loop(
                messages=[("user", "hi")], slot="chat", model=None,
                platform_keys=[], local_tools=[], max_steps=3,
            )
        ]
    )
    assert "RECOVERED" in out
    assert chat.calls == 3  # 2 瞬时失败 + 1 成功（无 tool_calls → 出最终文本）


class _FlakyStreamChat:
    """astream 前 fail_times 次（建连前）抛瞬时错误，之后正常逐块吐。"""

    def __init__(self, fail_times: int, exc: Exception, chunks: list[str]) -> None:
        self.fail_times = fail_times
        self.exc = exc
        self.chunks = chunks
        self.attempts = 0

    def bind_tools(self, schemas):  # noqa: ANN001
        return self

    async def astream(self, messages, **kw):  # noqa: ANN001
        self.attempts += 1
        if self.attempts <= self.fail_times:
            raise self.exc  # 首块前失败 → 可重试

        class _Chunk:
            def __init__(self, c: str) -> None:
                self.content = c
                self.usage_metadata = {"total_tokens": 1}

        for c in self.chunks:
            yield _Chunk(c)


@pytest.mark.asyncio
async def test_stream_retries_establishment_then_succeeds(monkeypatch) -> None:
    monkeypatch.setattr(rt, "_RETRY_BASE_DELAY", 0)
    chat = _FlakyStreamChat(fail_times=2, exc=_RateLimit("429"), chunks=["你好", "世界"])
    run = AgentRun(
        transport=_FlakyTransport(chat), agent_key="x", query="q", messages=[],
        history=[], session_id=None, config={}, retries=3,
    )
    out = "".join([c async for c in run.stream(user="hi")])
    assert out == "你好世界"
    assert chat.attempts == 3  # 2 建连瞬时失败 + 1 成功


@pytest.mark.asyncio
async def test_stream_does_not_retry_after_first_chunk(monkeypatch) -> None:
    """已吐 chunk 后失败无法干净重试（半截输出）→ 传播，不重试。"""
    monkeypatch.setattr(rt, "_RETRY_BASE_DELAY", 0)

    class _MidFailChat:
        def __init__(self) -> None:
            self.attempts = 0

        def bind_tools(self, schemas):  # noqa: ANN001
            return self

        async def astream(self, messages, **kw):  # noqa: ANN001
            self.attempts += 1

            class _Chunk:
                content = "片段"
                usage_metadata = {"total_tokens": 1}

            yield _Chunk()
            raise _RateLimit("mid-stream 429")

    chat = _MidFailChat()
    run = AgentRun(
        transport=_FlakyTransport(chat), agent_key="x", query="q", messages=[],
        history=[], session_id=None, config={}, retries=3,
    )
    got: list[str] = []
    with pytest.raises(_RateLimit):
        async for c in run.stream(user="hi"):
            got.append(c)
    assert got == ["片段"] and chat.attempts == 1  # 半截不重试
