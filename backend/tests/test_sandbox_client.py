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


@pytest.mark.asyncio
async def test_complete_does_chat_rpc_roundtrip():
    sent: list = []

    async def fake_rpc(frame):
        sent.append(frame)
        return {"t": "rpc_result", "id": frame["id"], "ok": True, "data": "沙箱回答"}

    t = SandboxClientTransport(rpc_fn=fake_rpc, emit_fn=lambda e: None)
    out = await _run(t).complete(system="s", user="问题")
    assert out == "沙箱回答"
    assert sent[0]["t"] == "rpc" and sent[0]["method"] == "chat"
    assert sent[0]["id"] == 1
    assert sent[0]["args"]["messages"][-1]["content"] == "问题"  # user 消息过线


@pytest.mark.asyncio
async def test_emit_writes_event_frame():
    from chameleon.providers.base.types import StreamEvent, StreamEventType

    frames: list = []

    async def fake_rpc(f):
        return {"ok": True, "data": ""}

    t = SandboxClientTransport(rpc_fn=fake_rpc, emit_fn=frames.append)
    t.emit(StreamEvent(type=StreamEventType.tool_call, data={"name": "calc"}))
    assert frames[0]["t"] == "event"
    assert frames[0]["event"]["data"] == {"name": "calc"}


@pytest.mark.asyncio
async def test_rpc_error_raises():
    async def fake_rpc(f):
        return {"ok": False, "error": "越权: 未声明 model"}

    t = SandboxClientTransport(rpc_fn=fake_rpc, emit_fn=lambda e: None)
    with pytest.raises(RuntimeError, match="越权"):
        await _run(t).complete(system="s", user="q")


def test_frame_codec_roundtrip():
    obj = {"t": "rpc", "id": 3, "args": {"x": "中文"}}
    assert decode_frame(encode_frame(obj)) == obj
    assert encode_frame(obj).endswith(b"\n")  # 换行分帧
