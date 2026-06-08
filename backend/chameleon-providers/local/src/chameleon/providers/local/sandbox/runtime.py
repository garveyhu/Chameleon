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


def _to_messages(raw: list[dict[str, Any]]) -> list[Any]:
    """OpenAI 风格消息 dict → LangChain 消息（含 assistant tool_calls / tool 回填）。"""
    from langchain_core.messages import (
        AIMessage,
        HumanMessage,
        SystemMessage,
        ToolMessage,
    )

    out: list[Any] = []
    for m in raw:
        role = m.get("role")
        content = m.get("content") or ""
        if role == "system":
            out.append(SystemMessage(content=content))
        elif role == "assistant":
            tcs = m.get("tool_calls") or []
            if tcs:
                out.append(AIMessage(content=content, tool_calls=[
                    {"name": t["name"], "args": t.get("args") or {}, "id": t.get("id")} for t in tcs
                ]))
            else:
                out.append(AIMessage(content=content))
        elif role == "tool":
            out.append(ToolMessage(content=content, tool_call_id=m.get("tool_call_id") or m.get("id") or ""))
        else:
            out.append(HumanMessage(content=content))
    return out


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
        if method == "chat_tools":
            from chameleon.integrations.tools.loop import (
                bind_schemas,
                extract_tool_calls,
                tool_schemas,
            )

            msgs = _to_messages(args.get("messages", []))
            model = broker.chat_model(slot=args.get("slot"), model=args.get("model"))
            schemas = tool_schemas(args.get("platform_tool_keys") or []) + (
                args.get("local_tool_schemas") or []
            )
            client = bind_schemas(model, schemas) if schemas else model
            resp = await client.ainvoke(msgs)
            return {"ok": True, "data": {
                "content": getattr(resp, "content", "") or "",
                "tool_calls": extract_tool_calls(resp),
            }}
        if method == "run_tool":
            from chameleon.integrations.tools import run_tool

            name = args.get("name", "")
            # scope 红线：只能调该 agent 声明的平台工具，不可越权
            declared = set(getattr(broker, "_tool_keys", []) or [])
            if declared and name not in declared:
                return {"ok": False, "error": f"越权：未声明的工具 {name}"}
            res = await run_tool(name, args.get("args") or {}, caller="sandbox")
            return {"ok": True, "data": res}
        if method == "memory_get":
            return {"ok": True, "data": await broker.memory_get(args.get("key", ""))}
        if method == "memory_set":
            await broker.memory_set(args.get("key", ""), args.get("value"))
            return {"ok": True, "data": None}
        if method == "memory_all":
            return {"ok": True, "data": await broker.memory_all()}
        if method == "call_agent":
            ans = await broker.call_agent(args.get("target", ""), input=args.get("input", ""))
            return {"ok": True, "data": ans}
        if method == "media_generate":
            r = await broker.media_generate(
                kind=args.get("kind", "image"), prompt=args.get("prompt", ""),
                slot=args.get("slot"), model=args.get("model"),
                params=args.get("params"), input_images=args.get("input_images"),
            )
            return {"ok": True, "data": {
                "url": r.url, "object_key": r.object_key, "media_kind": r.media_kind,
                "mime_type": r.mime_type, "filename": r.filename,
            }}
        if method == "kb_search":
            docs = await broker.kb_search(
                args.get("query", ""), kbs=args.get("kbs"), top_k=args.get("top_k"),
                min_score=args.get("min_score", 0.0), mode=args.get("mode"),
                rerank=args.get("rerank"), expand=args.get("expand", 0), hyde=args.get("hyde", False),
            )
            return {"ok": True, "data": [
                {"text": d.text, "score": d.score, "source": d.source, "metadata": d.metadata}
                for d in docs
            ]}
        return {"ok": False, "error": f"sandbox 未支持的 rpc: {method}"}
    except Exception as e:  # noqa: BLE001
        logger.warning("sandbox rpc 解析失败 method={}: {}", method, e)
        return {"ok": False, "error": "资源调用失败"}  # 脱敏


async def _stream_chat(broker: Any, proc: Any, frame: dict[str, Any]) -> None:
    """chat_stream rpc：broker.astream 逐块回 stream_chunk 帧 + 末 rpc_result。"""
    rid = frame["id"]
    args = frame.get("args") or {}
    try:
        msgs = [(m.get("role", "user"), m.get("content", "")) for m in args.get("messages", [])]
        model = broker.chat_model(slot=args.get("slot"), model=args.get("model"))
        async for chunk in model.astream(msgs):
            text = getattr(chunk, "content", "") or ""
            if text:
                proc.stdin.write(encode_frame({"t": "stream_chunk", "id": rid, "chunk": text}))
                await proc.stdin.drain()
        proc.stdin.write(encode_frame({"t": "rpc_result", "id": rid, "ok": True, "data": None}))
    except Exception as e:  # noqa: BLE001
        logger.warning("sandbox chat_stream 失败: {}", e)
        proc.stdin.write(encode_frame({"t": "rpc_result", "id": rid, "ok": False, "error": "资源调用失败"}))
    await proc.stdin.drain()


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
                if frame.get("method") == "chat_stream":
                    await _stream_chat(broker, proc, frame)
                else:
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
