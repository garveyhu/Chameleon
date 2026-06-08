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


def _model_scope_error(broker: Any, model: str | None) -> str | None:
    """model 点名 scope 红线：不可信子进程不得点名未声明的模型（防越权烧钱）。

    声明集 = broker 绑定的模型 code（_bindings.values()）。model=None 走 slot 绑定链（受
    声明约束，放行）；点名 ∈ 声明集放行；声明集为空（无显式绑定）则无从约束，放行 + warn。
    """
    if not model:
        return None
    declared = {v for v in (getattr(broker, "_bindings", {}) or {}).values() if v}
    if not declared:
        logger.warning("sandbox model scope 无声明集，放行点名 {}", model)
        return None
    if model not in declared:
        return f"越权：未声明的模型 {model}"
    return None


def _scoped_tool_keys(broker: Any, requested: list[str] | None) -> list[str]:
    """平台工具 scope：请求集 ∩ agent 声明集（_tool_keys）。"""
    declared = set(getattr(broker, "_tool_keys", []) or [])
    return [k for k in (requested or []) if k in declared]


async def _resolve_rpc(broker: Any, frame: dict[str, Any]) -> dict[str, Any]:
    """主进程 broker 解析子进程的 ctx rpc，返 {ok, data|error}。带 scope 红线。"""
    method = frame.get("method")
    args = frame.get("args") or {}
    try:
        if method == "chat":
            err = _model_scope_error(broker, args.get("model"))
            if err:
                return {"ok": False, "error": err}
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

            err = _model_scope_error(broker, args.get("model"))
            if err:
                return {"ok": False, "error": err}
            msgs = _to_messages(args.get("messages", []))
            model = broker.chat_model(slot=args.get("slot"), model=args.get("model"))
            # 平台工具只绑声明集内的（与 run_tool scope 一致）
            schemas = tool_schemas(_scoped_tool_keys(broker, args.get("platform_tool_keys"))) + (
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
            # scope 红线：只能调该 agent 声明的平台工具（空声明=一个都不能调，全拒）
            declared = set(getattr(broker, "_tool_keys", []) or [])
            if name not in declared:
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
            # scope 红线：沙箱（不可信）只能调声明的子 agent（call_agents allow-list）；
            # 未声明=拒（防横向越权调任意 agent）。depth/budget 闸仍在 broker.call_agent 内。
            target = args.get("target", "")
            allowed = set(getattr(broker, "_call_agents", []) or [])
            if target not in allowed:
                return {"ok": False, "error": f"越权：未声明可调的子 agent {target}"}
            ans = await broker.call_agent(target, input=args.get("input", ""))
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
            # kb scope 红线：点名的 kbs 必须 ∈ agent 关联的 KB（越权的剔除）；不点名走
            # broker 的 linked KB（已受约束）。防不可信子进程检索任意/他人知识库。
            requested = args.get("kbs")
            scoped = requested
            if requested:
                from chameleon.integrations.knowledge import list_linked_kb_metas

                linked = {m.kb_key for m in await list_linked_kb_metas(broker._agent_key)}
                scoped = [k for k in requested if k in linked]
            docs = await broker.kb_search(
                args.get("query", ""), kbs=scoped, top_k=args.get("top_k"),
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
        err = _model_scope_error(broker, args.get("model"))
        if err:
            proc.stdin.write(encode_frame({"t": "rpc_result", "id": rid, "ok": False, "error": err}))
            await proc.stdin.drain()
            return
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
    # ⚠️ Phase 2 子进程隔离 = env 凭据擦除 + 进程 + CPU/内存限 + ctx 经 broker scope。
    # **不含**文件系统隔离（子进程仍可 open 盘上 .env/config 读凭据）+ 网络出站隔离。
    # 真"接不可信陌生人代码"需 Phase 3 docker（network=none + 只读 rootfs，见 #29/#30）。
    logger.warning(
        "agentkit sandbox（子进程）：env 凭据已擦除，但 FS/网络未隔离 —— 不可信代码请用 "
        "Phase 3 docker runtime；当前档适合半可信代码"
    )
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "chameleon.agentkit._sandbox_child",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=None,  # 继承父 stderr，避免管道缓冲死锁
        env=env,
        limit=8 * 1024 * 1024,  # 单帧上限 8MB（默认 64KiB 会让 yield 大文本/base64 崩）
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
            try:
                line = await asyncio.wait_for(proc.stdout.readline(), timeout=_CHILD_TIMEOUT)
            except (ValueError, asyncio.LimitOverrunError):
                # 单行超 limit（恶意/超大帧）→ 中止，不崩主流程
                logger.warning("sandbox 子进程帧超限，中止")
                yield StreamEvent(type=StreamEventType.error, data={"message": "智能体输出异常"})
                break
            if not line:
                break
            try:
                frame = decode_frame(line)
            except (ValueError, TypeError):
                logger.warning("sandbox 子进程畸形帧，中止")
                yield StreamEvent(type=StreamEventType.error, data={"message": "智能体输出异常"})
                break
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
