"""沙箱子进程 ctx transport 协议单测（T4-2 Phase 2 Slice 1a，内存假 rpc）。"""

from __future__ import annotations

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
