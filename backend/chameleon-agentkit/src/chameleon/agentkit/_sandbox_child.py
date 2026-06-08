"""沙箱子进程入口 —— `python -m chameleon.agentkit._sandbox_child`。

在隔离子进程里跑作者 handle(ctx)：从 stdin 读 init 帧（agent module/attr/input），import
作者 agent，建 SandboxClientTransport（ctx 资源调用经 stdio JSON-RPC 回主进程 broker），
跑 handle，把产出 / emit 帧化写 stdout，结束发 done。

子进程 env 已被主进程擦除（无凭据），仅经 broker 拿主进程授予的资源——即便作者代码恶意
也读不到 DATABASE_URL/密钥。协议见 docs/plans/2026-06-08-sandbox-phase2-design.md §2。
"""

from __future__ import annotations

import asyncio
import inspect
import sys
from typing import Any

from chameleon.agentkit._runtime import AgentRun
from chameleon.agentkit._sandbox_client import (
    SandboxClientTransport,
    decode_frame,
    encode_frame,
)


def _send(frame: dict[str, Any]) -> None:
    sys.stdout.buffer.write(encode_frame(frame))
    sys.stdout.buffer.flush()


async def _stdin_reader() -> asyncio.StreamReader:
    loop = asyncio.get_event_loop()
    reader = asyncio.StreamReader()
    await loop.connect_read_pipe(lambda: asyncio.StreamReaderProtocol(reader), sys.stdin.buffer)
    return reader


async def main() -> None:
    import importlib

    reader = await _stdin_reader()

    async def recv_fn() -> dict[str, Any]:
        line = await reader.readline()
        if not line:
            raise RuntimeError("broker 关闭（无响应）")
        return decode_frame(line)

    init = decode_frame(await reader.readline())
    try:
        mod = importlib.import_module(init["module"])
        target = getattr(mod, init["attr"])
        manifest = target.__agent_manifest__
        transport = SandboxClientTransport(send_fn=_send, recv_fn=recv_fn, emit_fn=_send)
        run = AgentRun(
            transport=transport,
            agent_key=manifest.key,
            query=init.get("input", ""),
            messages=[],
            history=[],
            session_id=init.get("session_id"),
            config=init.get("config") or {},
        )
        result = target().handle(run) if manifest.is_class else target(run)
        if inspect.isasyncgen(result):
            async for chunk in result:
                _send({"t": "event", "event": {"type": "delta", "data": {"text": chunk}}})
        else:
            text = await result
            if text:
                _send({"t": "event", "event": {"type": "delta", "data": {"text": text}}})
        _send({"t": "done", "ok": True})
    except Exception as e:  # noqa: BLE001
        # 脱敏：只回异常类型，不回堆栈
        _send({"t": "done", "ok": False, "error": type(e).__name__})


if __name__ == "__main__":
    asyncio.run(main())
