"""Playground 调试服务：直调 LLM 流式 + 可选 KB context prepend

溯源化（块5）：必须绑定一个 owner key，按 channel='playground' 落 ChatSession +
messages + call_log 根行 → Trace / 会话 列表与嵌入式同构。
"""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timezone

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from loguru import logger
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.api.exceptions import (
    BusinessError,
    ResultCode,
    ValidationError,
)
from chameleon.core.api.sse_events import (
    UsagePayload,
    event_delta,
    event_end,
    event_meta,
)
from chameleon.core.observe import (
    TraceContext,
    reset_trace_context,
    set_trace_context,
)
from chameleon.data.models import ChatSession, KnowledgeBase, LLMModel, Message
from chameleon.data.utils.snowflake import next_session_id
from chameleon.integrations.llms.factory import resolve_llm
from chameleon.system.api_key.service import (
    aggregate_generation_rollup,
    record_call,
)
from chameleon.system.kbs.document_service import search_chunks

PLAYGROUND_APP_ID = "playground"
PLAYGROUND_AGENT_KEY = "playground"
PLAYGROUND_TOP_K = 3
PLAYGROUND_CTX_HEADER = "以下是参考资料，请基于这些资料作答（无关时可忽略）：\n"


class SessionConfig(BaseModel):
    """会话级配置快照，落 ChatSession.meta.config。

    Playground 是 model-direct（无应用），配置跟会话走（ChatGPT 式）；resume 时
    前端读回此快照恢复 ParamPanel。bound_agent_key 仅记录「基于哪个应用预填」，运
    行时仍走 model-direct，owner key 不入此处（在 ChatSession.api_key_id 列）。
    """

    # 雪花 id 存字符串：避免 JSON number > 2^53 在前端 JSON.parse 丢精度
    model_id: str | None = None
    # 落解析后的 model code（即使模型行后续改动，reopen 仍确定）
    model_name: str | None = None
    system_prompt: str | None = None
    temperature: float | None = None
    top_p: float | None = None
    max_tokens: int | None = None
    kb_ids: list[int] = Field(default_factory=list)
    bound_agent_key: str | None = None


def _build_session_config(
    *,
    model_id: int | None,
    model_name: str | None,
    system_prompt: str | None,
    temperature: float,
    top_p: float | None,
    max_tokens: int | None,
    kb_ids: list[int],
    bound_agent_key: str | None,
) -> dict:
    """组装会话配置快照 dict（create + 每轮 update 共用，单一来源）。"""
    return SessionConfig(
        model_id=str(model_id) if model_id is not None else None,
        model_name=model_name,
        system_prompt=system_prompt or None,
        temperature=temperature,
        top_p=top_p,
        max_tokens=max_tokens,
        kb_ids=list(kb_ids or []),
        bound_agent_key=bound_agent_key,
    ).model_dump()


async def _append_message(
    session: AsyncSession,
    *,
    session_id: str,
    role: str,
    content: str,
    request_id: str | None = None,
    usage: dict | None = None,
    end_user_id: str | None = None,
) -> None:
    """直接落一条 message（playground 在 system 层，不走 api 层 sessions service）。"""
    next_seq = (
        await session.execute(
            select(func.coalesce(func.max(Message.seq), 0) + 1).where(
                Message.session_id == session_id
            )
        )
    ).scalar_one()
    session.add(
        Message(
            session_id=session_id,
            seq=next_seq,
            role=role,
            content=content,
            request_id=request_id,
            usage=usage,
            end_user_id=end_user_id,
            created_at=datetime.now(timezone.utc),
        )
    )
    await session.flush()


async def get_model_name(session: AsyncSession, model_id: int) -> str:
    row = (
        await session.execute(select(LLMModel).where(LLMModel.id == model_id))
    ).scalar_one_or_none()
    if row is None:
        raise BusinessError(ResultCode.Fail, message=f"model 不存在: {model_id}")
    return row.code


async def build_kb_context(
    session: AsyncSession, *, query: str, kb_ids: list[int]
) -> tuple[str, list[dict]]:
    """从所选 KB 检索 top chunks → (拼好的 system 前缀文本, 结构化引用列表)。

    引用结构化返回（[{source, ref, content}]），供 invoke_stream 落成 retriever
    观测节点；不再让前端从拼接字符串里硬拆，跨渠道通用。
    """
    if not kb_ids:
        return "", []
    pieces: list[str] = []
    citations: list[dict] = []
    for kb_id in kb_ids:
        # 校验 kb 存在 + 取 default mode
        kb = (
            await session.execute(
                select(KnowledgeBase).where(
                    KnowledgeBase.id == kb_id,
                    KnowledgeBase.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if kb is None:
            continue
        try:
            hits = await search_chunks(
                session,
                kb_id=kb.id,
                query=query,
                top_k=PLAYGROUND_TOP_K,
                mode=kb.recall_mode,
            )
        except Exception:  # noqa: BLE001
            logger.exception(
                "playground kb retrieval failed | kb={} | query_len={}",
                kb_id,
                len(query),
            )
            continue
        for h in hits:
            pieces.append(
                f"[{kb.name}#{h['doc_id']}#{h['seq']}] {h['content']}"
            )
            # 召回模式 + 相关度分数透出：向量=相似度 / 关键词=BM25 / 混合=RRF；
            # 命中的子分数（vector/bm25/rerank）按存在透出，溯源里可读出"为什么召回"
            cit: dict = {
                "source": kb.name,
                "ref": f"{h['doc_id']}#{h['seq']}",
                "content": h["content"],
                "mode": kb.recall_mode,
            }
            if h.get("score") is not None:
                cit["score"] = round(float(h["score"]), 4)
            for sk in ("vector_score", "bm25_score", "rerank_score"):
                sv = h.get(sk)
                if sv is not None:
                    cit[sk] = round(float(sv), 4)
            citations.append(cit)
    if not pieces:
        return "", []
    return PLAYGROUND_CTX_HEADER + "\n\n".join(pieces) + "\n\n", citations


def build_messages(
    *,
    system_prompt: str | None,
    kb_context: str,
    messages: list[dict],
) -> list:
    """把 system + (kb_context 拼到 system 前缀) + 历史 message → LangChain messages"""
    out = []
    sys_parts: list[str] = []
    if kb_context:
        sys_parts.append(kb_context)
    if system_prompt:
        sys_parts.append(system_prompt)
    if sys_parts:
        out.append(SystemMessage(content="\n\n".join(sys_parts)))

    for m in messages:
        role = m.get("role")
        content = m.get("content", "")
        if role == "user":
            out.append(HumanMessage(content=content))
        elif role == "assistant":
            out.append(AIMessage(content=content))
        elif role == "system":
            # 已合并在 system_prompt；忽略
            continue
        else:
            raise ValidationError(message=f"unsupported message role: {role}")
    if not out or not isinstance(out[-1], HumanMessage):
        raise ValidationError(message="messages 末条必须是 user")
    return out


async def invoke_stream(
    session: AsyncSession,
    *,
    api_key_id: int | None,
    session_id: str | None,
    operator_user_id: int | None = None,
    model_id: int | None,
    model_name: str | None,
    system_prompt: str | None,
    temperature: float,
    top_p: float | None,
    max_tokens: int | None,
    messages: list[dict],
    kb_ids: list[int],
    bound_agent_key: str | None = None,
    persist_config: bool = True,
) -> AsyncIterator[dict]:
    """完整 playground 调用编排：绑 key 溯源 → 建/续会话 → KB context → 流式调用。

    溯源（块5）：channel='playground'，落 ChatSession + user/assistant messages +
    call_log 根行（token/cost 从 generation 子行 rollup）。抛 ValidationError /
    BusinessError 由上层 sse_response 兜底成 error chunk。
    """
    if api_key_id is None:
        raise ValidationError(message="Playground 必须绑定一个 Key 用于溯源")

    resolved_model = model_name
    if not resolved_model:
        if model_id is None:
            raise ValidationError(message="必须提供 model_id 或 model_name")
        resolved_model = await get_model_name(session, model_id)

    last_user = next((m for m in reversed(messages) if m.get("role") == "user"), None)
    if last_user is None:
        raise ValidationError(message="messages 中至少有一条 user")
    raw = last_user.get("content", "")
    user_text = raw if isinstance(raw, str) else "[多模态消息]"
    # 操作者即终端用户：登录 admin id 落 end_user_id（溯源「谁跑的」）
    operator_eid = str(operator_user_id) if operator_user_id is not None else None

    # 会话配置快照（落 meta.config，resume 时前端读回恢复 ParamPanel）
    cfg = _build_session_config(
        model_id=model_id,
        model_name=resolved_model,
        system_prompt=system_prompt,
        temperature=temperature,
        top_p=top_p,
        max_tokens=max_tokens,
        kb_ids=kb_ids,
        bound_agent_key=bound_agent_key,
    )

    # 会话：续接已有 / 新建（新建时用首条 user 文本当标题 + 落初始配置）
    if not session_id:
        sid = next_session_id()
        session.add(
            ChatSession(
                session_id=sid,
                agent_key=PLAYGROUND_AGENT_KEY,
                app_id=PLAYGROUND_APP_ID,
                api_key_id=api_key_id,
                end_user_id=operator_eid,
                title=user_text[:30] or None,
                meta={"config": cfg},
            )
        )
        await session.flush()
        session_id = sid
        await session.commit()

    request_id = uuid.uuid4().hex
    # 流头 meta：把 session_id / request_id 透给前端（前端按列续接会话）
    yield event_meta(
        session_id=session_id, request_id=request_id, model=resolved_model
    )

    # 落 user 消息（独立小事务，失败不阻塞推理）
    try:
        await _append_message(
            session,
            session_id=session_id,
            role="user",
            content=user_text,
            request_id=request_id,
            end_user_id=operator_eid,
        )
        await session.commit()
    except Exception:  # noqa: BLE001
        logger.exception("playground persist user msg failed | sid=%s", session_id)

    token = set_trace_context(
        TraceContext(
            request_id=request_id,
            channel="playground",
            app_id=PLAYGROUND_APP_ID,
            api_key_id=api_key_id,
            agent_key=PLAYGROUND_AGENT_KEY,
            session_id=session_id,
            end_user_id=operator_eid,
            user_id=operator_user_id,
        )
    )
    started = time.monotonic()
    ok = True
    answer_parts: list[str] = []
    try:
        kb_started = time.monotonic()
        kb_context, citations = await build_kb_context(
            session, query=user_text, kb_ids=kb_ids
        )
        kb_duration_ms = int((time.monotonic() - kb_started) * 1000)
        # KB 召回落成 retriever 观测节点（结构化引用，挂在根 trace 下，与 generation 平级）
        if citations:
            try:
                await record_call(
                    session,
                    request_id=f"{request_id}.kb",
                    app_id=PLAYGROUND_APP_ID,
                    agent_key=PLAYGROUND_AGENT_KEY,
                    session_id=session_id,
                    channel="playground",
                    stream=False,
                    success=True,
                    code=0,
                    error_message=None,
                    duration_ms=kb_duration_ms,
                    request_payload={"query": user_text[:500], "kb_ids": kb_ids},
                    response_payload={"citations": citations},
                    parent_id=request_id,
                    observation_type="retriever",
                    api_key_id=api_key_id,
                    end_user_id=operator_eid,
                    user_id=operator_user_id,
                )
                await session.commit()
            except Exception:  # noqa: BLE001
                logger.exception("playground retriever node persist failed")
        lc_messages = build_messages(
            system_prompt=system_prompt,
            kb_context=kb_context,
            messages=messages,
        )
        async for chunk in _stream_llm(
            session,
            model_name=resolved_model,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            messages=lc_messages,
        ):
            if chunk.get("delta"):
                answer_parts.append(chunk["delta"])
            yield chunk
    except Exception:
        ok = False
        raise
    finally:
        # 落 assistant 消息 + 写 playground 根 trace（token/cost 从 generation 子行 SUM）
        try:
            p, c, t, cost, fmodel = await aggregate_generation_rollup(
                session, request_id
            )
            answer = "".join(answer_parts)
            if answer:
                await _append_message(
                    session,
                    session_id=session_id,
                    role="assistant",
                    content=answer,
                    request_id=request_id,
                    usage={"input_tokens": p, "output_tokens": c}
                    if t is not None
                    else None,
                    end_user_id=operator_eid,
                )
            # 每轮刷新 last_message_at；仅 persist_config 时覆盖配置快照
            # （translate / 临时指令等 transient override 不写，避免污染会话配置）
            values: dict = {"last_message_at": datetime.now(timezone.utc)}
            if persist_config:
                values["meta"] = {"config": cfg}
            await session.execute(
                update(ChatSession)
                .where(ChatSession.session_id == session_id)
                .values(**values)
            )
            await record_call(
                session,
                request_id=request_id,
                app_id=PLAYGROUND_APP_ID,
                agent_key=PLAYGROUND_AGENT_KEY,
                session_id=session_id,
                channel="playground",
                stream=True,
                success=ok,
                code=0 if ok else 500,
                error_message=None,
                duration_ms=int((time.monotonic() - started) * 1000),
                prompt_tokens=p,
                completion_tokens=c,
                total_tokens=t,
                request_payload={"question": user_text[:1000]},
                # 子节点输出回灌根 trace：根行输出 = 最终回答（与子 generation 一致）
                response_payload={"output": answer[:4000]} if answer else None,
                observation_type="trace",
                api_key_id=api_key_id,
                end_user_id=operator_eid,
                user_id=operator_user_id,
                model_code=fmodel or resolved_model,
                cost_usd=cost,
            )
            await session.commit()
        except Exception:  # noqa: BLE001
            logger.exception("playground trace/persist failed | rid=%s", request_id)
        reset_trace_context(token)


async def _stream_llm(
    session: AsyncSession,
    *,
    model_name: str,
    temperature: float,
    top_p: float | None,
    max_tokens: int | None,
    messages: list,
) -> AsyncIterator[dict]:
    """直接走 LLM .astream，逐 token yield {"delta": str}；末尾 {"end": True, "usage": ...}。"""
    # #30：per-request 经 channel 路由（含 C7 key 轮转）解析 LLM；无 channel 回退 cache
    llm = await resolve_llm(
        model_name, session=session, temperature=temperature, max_tokens=max_tokens
    )
    # 覆盖运行时参数（不污染 cache）
    bound_kwargs: dict = {"temperature": temperature}
    if top_p is not None:
        bound_kwargs["top_p"] = top_p
    if max_tokens is not None:
        bound_kwargs["max_tokens"] = max_tokens
    bound = llm.bind(**bound_kwargs)

    usage: UsagePayload | None = None
    async for chunk in bound.astream(messages):
        text = getattr(chunk, "content", None)
        if text:
            yield event_delta(text)
        # langchain_openai 流末带 usage_metadata
        u = getattr(chunk, "usage_metadata", None)
        if u:
            usage = UsagePayload.from_dict(u)
    yield event_end(usage=usage)
