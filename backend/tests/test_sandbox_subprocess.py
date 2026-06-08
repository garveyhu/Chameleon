"""沙箱子进程 IPC e2e（T4-2 Phase 2 Slice 1b）：真实子进程 + 环境擦除验证。

手搭 parent（fake broker）驱动真实子进程：验 ctx.complete 经 stdio chat rpc 往返 + 作者
代码在子进程读不到 DATABASE_URL（凭据隔离）。
"""

from __future__ import annotations

import asyncio
import os
import sys
import textwrap

import pytest

from chameleon.agentkit._sandbox_client import decode_frame, encode_frame
from chameleon.providers.local.sandbox import scrub_env

_AGENT = textwrap.dedent(
    '''
    import os
    from chameleon.agentkit import agent, AgentRun, ModelSlot

    @agent(key="_sbx_e2e", name="t", models=[ModelSlot("chat", "c")])
    async def handle(ctx: AgentRun):
        db = os.environ.get("DATABASE_URL", "<scrubbed>")
        ans = await ctx.complete(system="s", user=ctx.query)
        yield f"{ans}|db={db}"
    '''
)


@pytest.mark.asyncio
async def test_subprocess_sandbox_ipc_and_env_scrub(tmp_path, monkeypatch):
    (tmp_path / "sbx_agent_mod.py").write_text(_AGENT, encoding="utf-8")
    monkeypatch.setenv("DATABASE_URL", "postgres://secret@h/db")  # parent 有，child 不应有
    env = scrub_env(
        dict(os.environ),
        extra={"PYTHONPATH": os.pathsep.join([str(tmp_path), *sys.path])},
    )
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "chameleon.agentkit._sandbox_child",
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
        stderr=None, env=env,
    )
    assert proc.stdin and proc.stdout
    proc.stdin.write(encode_frame({"module": "sbx_agent_mod", "attr": "handle", "input": "问题"}))
    await proc.stdin.drain()

    deltas: list[str] = []
    done = None
    while True:
        line = await asyncio.wait_for(proc.stdout.readline(), timeout=30)
        if not line:
            break
        frame = decode_frame(line)
        if frame["t"] == "rpc" and frame["method"] == "chat":
            # fake broker：回 chat 内容（不连真模型）
            proc.stdin.write(
                encode_frame({"t": "rpc_result", "id": frame["id"], "ok": True, "data": "FAKE_LLM"})
            )
            await proc.stdin.drain()
        elif frame["t"] == "event" and frame["event"]["type"] == "delta":
            deltas.append(frame["event"]["data"]["text"])
        elif frame["t"] == "done":
            done = frame
            break
    await asyncio.wait_for(proc.wait(), timeout=10)

    assert done and done["ok"] is True
    text = "".join(deltas)
    assert "FAKE_LLM" in text  # ctx.complete 经 stdio chat rpc 往返成功
    assert "db=<scrubbed>" in text  # 凭据隔离：子进程读不到 DATABASE_URL
