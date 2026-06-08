"""沙箱子进程 ctx transport 协议单测（T4-2 Phase 2 Slice 1a，内存假 rpc）。"""

from __future__ import annotations

import asyncio

import pytest

from chameleon.agentkit._runtime import AgentRun
from chameleon.agentkit._sandbox_client import (
    SandboxClientTransport,
    decode_frame,
    encode_frame,
)


def _run(t: SandboxClientTransport) -> AgentRun:
    return AgentRun(
        transport=t, agent_key="x", query="q",
        messages=[], history=[], session_id=None, config={},
    )


class _FakeIO:
    """内存假 stdio：send 收集帧，recv 按最近 rpc 调 responder 产响应帧。"""

    def __init__(self, responder):
        self.sent: list = []
        self._responder = responder
        self._pending: list = []

    def send(self, frame):
        self.sent.append(frame)

    async def recv(self):
        if self._pending:
            return self._pending.pop(0)
        frames = self._responder(self.sent[-1])
        self._pending = list(frames) if isinstance(frames, list) else [frames]
        return self._pending.pop(0)


@pytest.mark.asyncio
async def test_complete_does_chat_rpc_roundtrip():
    io = _FakeIO(lambda f: {"t": "rpc_result", "id": f["id"], "ok": True, "data": "沙箱回答"})
    t = SandboxClientTransport(send_fn=io.send, recv_fn=io.recv, emit_fn=lambda e: None)
    out = await _run(t).complete(system="s", user="问题")
    assert out == "沙箱回答"
    assert io.sent[0]["t"] == "rpc" and io.sent[0]["method"] == "chat"
    assert io.sent[0]["id"] == 1
    assert io.sent[0]["args"]["messages"][-1]["content"] == "问题"  # user 消息过线


@pytest.mark.asyncio
async def test_stream_yields_chunks():
    def responder(f):
        rid = f["id"]
        return [
            {"t": "stream_chunk", "id": rid, "chunk": "你"},
            {"t": "stream_chunk", "id": rid, "chunk": "好"},
            {"t": "rpc_result", "id": rid, "ok": True, "data": None},
        ]

    io = _FakeIO(responder)
    t = SandboxClientTransport(send_fn=io.send, recv_fn=io.recv, emit_fn=lambda e: None)
    chunks = [c async for c in _run(t).stream(system="s", user="q")]
    assert "".join(chunks) == "你好"
    assert io.sent[0]["method"] == "chat_stream"


@pytest.mark.asyncio
async def test_kb_search_returns_docs():
    io = _FakeIO(lambda f: {"t": "rpc_result", "id": f["id"], "ok": True,
                            "data": [{"text": "命中", "score": 0.9, "source": "doc1"}]})
    t = SandboxClientTransport(send_fn=io.send, recv_fn=io.recv, emit_fn=lambda e: None)
    docs = await t.kb_search("查询", kbs=["kb1"], mode="hybrid")
    assert len(docs) == 1 and docs[0].text == "命中" and docs[0].score == 0.9
    assert io.sent[0]["method"] == "kb_search" and io.sent[0]["args"]["mode"] == "hybrid"


@pytest.mark.asyncio
async def test_run_tool_loop_local_tool_and_reframe():
    from chameleon.agentkit import tool

    @tool(name="sbxcalc", description="算")
    async def sbxcalc(x: int) -> dict:
        return {"v": x * 2}

    state = {"n": 0}

    def responder(f):
        rid = f["id"]
        if f["method"] == "chat_tools":
            state["n"] += 1
            if state["n"] == 1:
                return {"t": "rpc_result", "id": rid, "ok": True, "data": {
                    "content": "", "tool_calls": [{"name": "sbxcalc", "args": {"x": 5}, "id": "c1"}]}}
            return {"t": "rpc_result", "id": rid, "ok": True, "data": {"content": "结果是10", "tool_calls": []}}
        return {"t": "rpc_result", "id": rid, "ok": True, "data": {}}

    io = _FakeIO(responder)
    emitted: list = []
    t = SandboxClientTransport(send_fn=io.send, recv_fn=io.recv, emit_fn=emitted.append)
    chunks = [
        c
        async for c in t.run_tool_loop(
            messages=[("user", "算 5*2")], slot="chat", model=None,
            platform_keys=[], local_tools=[sbxcalc.__tool_spec__], max_steps=4,
        )
    ]
    assert "结果是10" in "".join(chunks)
    # 本地 @tool 在子进程执行（不走 run_tool rpc），结果经 tool_result 事件帧
    assert any(
        e["event"]["type"] == "tool_result" and e["event"]["data"]["result"]["data"] == {"v": 10}
        for e in emitted
    )


@pytest.mark.asyncio
async def test_memory_call_agent_media_rpc():
    seen: list = []

    def responder(f):
        seen.append((f["method"], f.get("args")))
        rid = f["id"]
        data = {
            "memory_get": "记住的值",
            "memory_all": {"k": "v"},
            "call_agent": "子答案",
            "media_generate": {"url": "minio://x", "object_key": "k", "media_kind": "image"},
            "memory_set": None,
        }.get(f["method"])
        return {"t": "rpc_result", "id": rid, "ok": True, "data": data}

    io = _FakeIO(responder)
    t = SandboxClientTransport(send_fn=io.send, recv_fn=io.recv, emit_fn=lambda e: None)
    assert await t.memory_get("k") == "记住的值"
    await t.memory_set("k", "v")
    assert await t.memory_all() == {"k": "v"}
    assert await t.call_agent("sub", input="问") == "子答案"
    media = await t.media_generate(kind="image", prompt="猫")
    assert media.url == "minio://x" and media.media_kind == "image"
    methods = [m for m, _ in seen]
    assert {"memory_get", "memory_set", "memory_all", "call_agent", "media_generate"} <= set(methods)


@pytest.mark.asyncio
async def test_emit_writes_event_frame():
    from chameleon.providers.base.types import StreamEvent, StreamEventType

    frames: list = []
    io = _FakeIO(lambda f: {"ok": True, "data": ""})
    t = SandboxClientTransport(send_fn=io.send, recv_fn=io.recv, emit_fn=frames.append)
    t.emit(StreamEvent(type=StreamEventType.tool_call, data={"name": "calc"}))
    assert frames[0]["t"] == "event"
    assert frames[0]["event"]["data"] == {"name": "calc"}


@pytest.mark.asyncio
async def test_rpc_error_raises():
    io = _FakeIO(lambda f: {"t": "rpc_result", "id": f["id"], "ok": False, "error": "越权: 未声明 model"})
    t = SandboxClientTransport(send_fn=io.send, recv_fn=io.recv, emit_fn=lambda e: None)
    with pytest.raises(RuntimeError, match="越权"):
        await _run(t).complete(system="s", user="q")


def test_frame_codec_roundtrip():
    obj = {"t": "rpc", "id": 3, "args": {"x": "中文"}}
    assert decode_frame(encode_frame(obj)) == obj
    assert encode_frame(obj).endswith(b"\n")  # 换行分帧


@pytest.mark.asyncio
async def test_concurrent_rpc_channel_lock_no_frame_steal():
    """评审7 🟠 根治：并发 _rpc 经通道锁串行化，互不偷帧（即便 recv 返回序与发送序相反）。"""
    from chameleon.agentkit._sandbox_client import SandboxClientTransport

    sent: list[int] = []  # 已发未答的 rid

    def _send(frame):
        if frame.get("t") == "rpc":
            sent.append(frame["id"])

    async def _recv():
        # LIFO 返回最近未答 rid 的结果——无锁会让先发的 rpc 偷到后发的帧/对方挂起；
        # 有锁时任一时刻只一个 in-flight rid，恒正确。
        rid = sent.pop()
        return {"t": "rpc_result", "id": rid, "ok": True, "data": f"r{rid}"}

    t = SandboxClientTransport(send_fn=_send, recv_fn=_recv, emit_fn=lambda f: None)
    a, b = await asyncio.gather(t._rpc("m", {}), t._rpc("m", {}))
    # 两个并发 rpc 各拿到自己的结果（不混、不挂）；锁保证 in-flight 唯一
    assert {a, b} == {"r1", "r2"}
