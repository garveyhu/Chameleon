"""沙箱生产 parent —— spawn 隔离子进程 + broker 解析 ctx rpc（T4-2 Phase 2 Slice 1b-2）。

主进程持凭据 + 真实资源（broker = 该 agent 的 InProcessTransport）；子进程（无凭据）跑
handle，ctx 资源调用经 stdio JSON-RPC 回 broker 解析。parent 帧循环：rpc→broker 解析→
rpc_result；event→yield StreamEvent；done→结束。结束 terminate 子进程（防泄漏）。

Slice 1：解析 chat rpc（complete 底层）。stream/kb/工具/memory/media/call_agent 后续分片。
"""

from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import AsyncIterator
from typing import Any

from loguru import logger

from chameleon.agentkit._sandbox_client import decode_frame, encode_frame
from chameleon.providers.base.types import StreamEvent, StreamEventType
from chameleon.providers.local.sandbox.env import scrub_env

#: 子进程无响应墙钟超时（防死循环 / 卡住 handle 拖住 parent）
_CHILD_TIMEOUT = 120.0


async def _resolve_rpc(broker: Any, frame: dict[str, Any]) -> dict[str, Any]:
    """主进程 broker 解析子进程的 ctx rpc，返 {ok, data|error}。scope 校验 Slice 3 严格化。"""
    method = frame.get("method")
    args = frame.get("args") or {}
    try:
        if method == "chat":
            msgs = [(m.get("role", "user"), m.get("content", "")) for m in args.get("messages", [])]
            model = broker.chat_model(slot=args.get("slot"), model=args.get("model"))
            resp = await model.ainvoke(msgs)
            return {"ok": True, "data": getattr(resp, "content", "") or ""}
        return {"ok": False, "error": f"sandbox 未支持的 rpc: {method}"}
    except Exception as e:  # noqa: BLE001
        logger.warning("sandbox rpc 解析失败 method={}: {}", method, e)
        return {"ok": False, "error": "资源调用失败"}  # 脱敏


async def run_sandboxed(
    *,
    module: str,
    attr: str,
    query: str,
    broker: Any,
    session_id: str | None = None,
    config: dict[str, Any] | None = None,
    env_extra: dict[str, str] | None = None,
) -> AsyncIterator[StreamEvent]:
    """在隔离子进程跑 module:attr 的 handle，ctx 资源经 broker 解析，产出 StreamEvent 流。"""
    extra = {"PYTHONPATH": os.pathsep.join(p for p in sys.path if p)}
    extra.update(env_extra or {})
    env = scrub_env(dict(os.environ), extra=extra)
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "chameleon.agentkit._sandbox_child",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=None,  # 继承父 stderr，避免管道缓冲死锁
        env=env,
    )
    assert proc.stdin and proc.stdout
    proc.stdin.write(
        encode_frame(
            {"module": module, "attr": attr, "input": query,
             "session_id": session_id, "config": config or {}}
        )
    )
    await proc.stdin.drain()
    try:
        while True:
            line = await asyncio.wait_for(proc.stdout.readline(), timeout=_CHILD_TIMEOUT)
            if not line:
                break
            frame = decode_frame(line)
            t = frame.get("t")
            if t == "rpc":
                result = await _resolve_rpc(broker, frame)
                proc.stdin.write(encode_frame({"t": "rpc_result", "id": frame["id"], **result}))
                await proc.stdin.drain()
            elif t == "event":
                ev = frame["event"]
                yield StreamEvent(type=StreamEventType(ev["type"]), data=ev.get("data") or {})
            elif t == "done":
                if not frame.get("ok"):
                    logger.warning("sandbox handle 失败 module={}: {}", module, frame.get("error"))
                    yield StreamEvent(
                        type=StreamEventType.error,
                        data={"message": "智能体执行失败"},  # 脱敏
                    )
                break
    finally:
        if proc.returncode is None:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=5)
            except (TimeoutError, asyncio.TimeoutError):
                proc.kill()
