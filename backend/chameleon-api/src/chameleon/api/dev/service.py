"""agentkit 本地开发 dev 服务 —— 给 HttpDevTransport 回调的资源解析实现。

作者本地用 `agentkit chat` 跑自己的 @agent 代码，代码里的 ctx.llm/kb/tools 调用
经 HttpDevTransport 回调到这里：模型 / KB / 工具都用站内已配置资源，作者无需本地
凭据。仅开发态（设了 CHAMELEON_DEV_TOKEN）放行。

注：站内进程内运行走 InProcessTransport（providers-local），与此处是「同一份作者
代码两种跑法」的两端，逻辑各自独立、契约一致。
"""

from __future__ import annotations

from typing import Any

from chameleon.integrations.components import llm, llm_by_name, search_kb
from chameleon.integrations.tools.execute import run_tool
from chameleon.integrations.tools.loop import (
    bind_schemas,
    extract_tool_calls,
    extract_usage,
    tool_schemas,
)
from chameleon.integrations.tools.registry import all_tool_classes


def _to_messages(raw: list[dict[str, Any]]) -> list[Any]:
    """把 OpenAI 风格消息 dict 转 LangChain 消息（含 assistant tool_calls / tool 回填）。"""
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
                out.append(
                    AIMessage(
                        content=content,
                        tool_calls=[
                            {"name": t["name"], "args": t.get("args") or {}, "id": t.get("id")}
                            for t in tcs
                        ],
                    )
                )
            else:
                out.append(AIMessage(content=content))
        elif role == "tool":
            out.append(
                ToolMessage(
                    content=content, tool_call_id=m.get("tool_call_id") or m.get("id") or ""
                )
            )
        else:  # user / 其它一律当 user
            out.append(HumanMessage(content=content))
    return out


def _content_text(resp: Any) -> str:
    content = getattr(resp, "content", resp)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [
            b if isinstance(b, str) else (b.get("text", "") if isinstance(b, dict) else "")
            for b in content
        ]
        return "".join(parts)
    return str(content) if content is not None else ""


async def dev_llm(
    *,
    messages: list[dict[str, Any]],
    model: str | None = None,
    platform_tool_keys: list[str] | None = None,
    local_tool_schemas: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """一次模型调用（可绑工具），返回 {content, tool_calls, usage}。

    工具循环跑在客户端（HttpDevTransport）；本端只负责「绑工具 + 调一次 + 抽结果」。
    """
    base = llm_by_name(model) if model else llm()
    schemas = tool_schemas(list(platform_tool_keys or []))
    schemas.extend(local_tool_schemas or [])
    client = bind_schemas(base, schemas) if schemas else base
    resp = await client.ainvoke(_to_messages(messages))
    return {
        "content": _content_text(resp),
        "tool_calls": extract_tool_calls(resp),
        "usage": extract_usage(resp),
    }


async def dev_structured(
    *,
    messages: list[dict[str, Any]],
    schema: dict[str, Any],
    model: str | None = None,
) -> dict[str, Any]:
    """结构化输出：用客户端传来的 JSON schema 走 with_structured_output，返 dict。

    客户端（HttpDevTransport）持原 pydantic 类，拿到 dict 后自行 model_validate 还原实例
    —— dev 与站内 InProcessTransport 的 ctx.complete(schema=) 契约一致。
    """
    base = llm_by_name(model) if model else llm()
    # 客户端传的是 JSON schema dict（非 pydantic 类）→ langchain with_structured_output
    # 不直接吃裸 schema，包成 OpenAI function（name+parameters）走 function_calling。
    func = {
        "name": schema.get("title") or "structured_output",
        "description": schema.get("description", ""),
        "parameters": schema,
    }
    structured = base.with_structured_output(func, method="function_calling")
    resp = await structured.ainvoke(_to_messages(messages))
    if isinstance(resp, dict):
        return resp
    if hasattr(resp, "model_dump"):
        return resp.model_dump()
    return dict(resp)


async def dev_call_agent(
    *,
    target: str,
    input: str,
    run_id: str | None = None,
    resume_call_index: int | None = None,
    resume_answer: Any = None,
) -> dict[str, Any]:
    """dev 子智能体调用 + durable HITL 续跑（ctx.call_agent / resume 的 dev 实现）。

    本地自测时作者的 ctx.call_agent 经此回调，目标 agent 用站内已配置资源跑。durable agent
    若 ctx.ask_human 暂停 → 返 run_id + pending（call_index/prompt）；带 run_id + resume_call_index
    + resume_answer 重调即回填答案、journal 重放至 ask 点续跑。

    run_id 同时作 request_id（journal run 标识）+ session_id（durable journal 的持久化 scope）——
    resume 须复用首跑的 run_id 才能命中 journal。走 stream 扫描以捕获 pause 信号（invoke 聚合会丢）。
    """
    import uuid

    from chameleon.providers.base import AGENTS, PROVIDERS, InvokeContext
    from chameleon.providers.base.types import StreamEventType

    adef = AGENTS.get(target)
    if adef is None:
        return {"answer": "", "error": f"agent 不存在: {target}"}
    provider = PROVIDERS.get(adef.provider)
    if provider is None:
        return {"answer": "", "error": f"provider 未注册: {adef.provider}"}

    rid = run_id or uuid.uuid4().hex
    cvars: dict[str, Any] = {"_a2a_budget": 200_000, "_a2a_depth": 0}
    if resume_answer is not None and resume_call_index is not None:
        cvars["_resume_answer"] = resume_answer
        cvars["_resume_call_index"] = resume_call_index
    ctx = InvokeContext(
        agent_def=adef,
        input=input,
        history=[],
        session_id=rid,  # durable journal 的 scope；resume 须同 run_id 才命中
        provider_conv_id=None,
        context_vars=cvars,
        options={},
        app_id="dev",
        stream=True,
        request_id=rid,
    )
    parts: list[str] = []
    pending: dict[str, Any] | None = None
    try:
        async for ev in provider.stream(ctx):
            if ev.type == StreamEventType.delta:
                parts.append(ev.data.get("text", ""))
            elif (
                ev.type == StreamEventType.step
                and ev.data.get("name") == "human_input_pending"
            ):
                pending = {
                    "call_index": ev.data.get("call_index"),
                    "prompt": ev.data.get("prompt"),
                    "run_id": ev.data.get("run_id"),
                }
            elif ev.type == StreamEventType.error:
                return {"answer": "", "error": ev.data.get("message", "子智能体执行失败"),
                        "run_id": rid}
    except Exception:
        from loguru import logger

        logger.exception("dev call_agent 失败 target={}", target)
        return {"answer": "", "error": "子智能体执行失败", "run_id": rid}
    out: dict[str, Any] = {"answer": "".join(parts), "run_id": rid}
    if pending is not None:
        out["pending"] = pending
    return out


#: dev 记忆固定命名空间（本地自测无 end_user 身份；隔离于站内真实记忆）
_DEV_MEMORY_AGENT = "__dev__"
_DEV_MEMORY_SCOPE = "__dev__"


async def dev_memory(*, action: str, key: str = "", value: Any = None) -> Any:
    """dev 跨会话记忆 get/set/all —— 复用 AgentMemory 表的 dev 命名空间。"""
    from sqlalchemy import select

    from chameleon.data.infra.db import AsyncSessionLocal
    from chameleon.data.models import AgentMemory

    async with AsyncSessionLocal() as session:
        if action == "set":
            row = (
                await session.execute(
                    select(AgentMemory).where(
                        AgentMemory.agent_key == _DEV_MEMORY_AGENT,
                        AgentMemory.scope_ref == _DEV_MEMORY_SCOPE,
                        AgentMemory.mkey == key,
                    )
                )
            ).scalar_one_or_none()
            # 与 InProcessTransport 一致：JSON 列存 {"v": <值>} 信封（兼容标量）
            if row is None:
                session.add(
                    AgentMemory(
                        agent_key=_DEV_MEMORY_AGENT,
                        scope_ref=_DEV_MEMORY_SCOPE,
                        mkey=key,
                        value={"v": value},
                    )
                )
            else:
                row.value = {"v": value}
            await session.commit()
            return {"ok": True}
        rows = (
            await session.execute(
                select(AgentMemory).where(
                    AgentMemory.agent_key == _DEV_MEMORY_AGENT,
                    AgentMemory.scope_ref == _DEV_MEMORY_SCOPE,
                )
            )
        ).scalars().all()
        store = {
            r.mkey: (r.value.get("v") if isinstance(r.value, dict) else None) for r in rows
        }
        if action == "all":
            return store
        return store.get(key)  # get


async def dev_kb_search(
    *,
    query: str,
    kbs: list[str],
    top_k: int | None = None,
    min_score: float = 0.0,
    mode: str | None = None,
    rerank: bool | None = None,
    expand: int = 0,
    hyde: bool = False,
) -> list[dict[str, Any]]:
    """跨指定 KB 检索（dev 必须显式给 kbs，无 agent 关联上下文）。

    与站内一致：给了高级参数（mode/rerank/expand/hyde）且检索桥已注入则走 engine
    hybrid 管道，否则回退基础向量——保证「两种跑法」结果一致，不静默降级。
    """
    from chameleon.providers.base.retrieval_bridge import get_retrieve_fn

    retrieve_fn = get_retrieve_fn()
    use_advanced = retrieve_fn is not None and (
        mode is not None or rerank is not None or expand or hyde
    )
    merged: list[dict[str, Any]] = []
    for kb_key in kbs:
        if use_advanced:
            rows = await retrieve_fn(
                kb_key, query, top_k=top_k, min_score=min_score,
                mode=mode, rerank=rerank, expand=expand, hyde=hyde,
            )
            for r in rows:
                merged.append(
                    {
                        "text": r.get("content", ""),
                        "score": r.get("score", 0.0),
                        "source": f"{kb_key}#doc{r.get('doc_id', 0)}#{r.get('seq', 0)}",
                        "metadata": {
                            "kb_key": kb_key,
                            "doc_id": r.get("doc_id", 0),
                            "seq": r.get("seq", 0),
                        },
                    }
                )
        else:
            hits = await search_kb(kb_key, query, top_k=top_k, min_score=min_score)
            for h in hits:
                merged.append(
                    {
                        "text": h.content,
                        "score": h.score,
                        "source": f"{kb_key}#doc{h.doc_id}#{h.seq}",
                        "metadata": {"kb_key": kb_key, "doc_id": h.doc_id, "seq": h.seq},
                    }
                )
    merged.sort(key=lambda d: d.get("score", 0.0), reverse=True)
    return merged[: (top_k or 5)]


async def dev_exec_tool(*, name: str, args: dict[str, Any]) -> dict[str, Any]:
    """执行一个平台工具（走站内 registry + admin 闸门）。"""
    return await run_tool(name, args, caller="agentkit-dev")


def dev_list_tools() -> list[dict[str, Any]]:
    """列平台已注册工具（key + description）。"""
    return [
        {"tool_key": k, "description": cls.description}
        for k, cls in sorted(all_tool_classes().items())
    ]
