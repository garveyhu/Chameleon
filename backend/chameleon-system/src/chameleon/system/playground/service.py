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
    ObservationType,
    TraceContext,
    reset_trace_context,
    set_trace_context,
)
from chameleon.data.constants import Channel
from chameleon.data.infra.object_store import stash_media_urls
from chameleon.data.models import ChatSession, KnowledgeBase, LLMModel, Message
from chameleon.data.utils.snowflake import next_session_id
from chameleon.integrations.llms.factory import resolve_llm
from chameleon.integrations.observe.aspect import record_scope
from chameleon.system.api_key.service import (
    aggregate_generation_rollup,
    record_call,
)
from chameleon.system.kbs.document_service import search_chunks
from chameleon.system.pricing import resolve_agent_media_cost

PLAYGROUND_APP_ID = "playground"
PLAYGROUND_AGENT_KEY = "playground"
PLAYGROUND_TOP_K = 3
PLAYGROUND_CTX_HEADER = "以下是参考资料，请基于这些资料作答（无关时可忽略）：\n"

# H1 rewrite：基于单条回答即时改写 System Prompt 的 channel='eval' 上下文锚点。
EVAL_APP_ID = "__eval__"


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
    # 调用模式（生图/视频等生成应用）：非空则 reopen 时前端恢复为「调用应用」模式
    invoke_agent_key: str | None = None


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
    invoke_agent_key: str | None = None,
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
        invoke_agent_key=invoke_agent_key,
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
            # 落库归一：生图返回的 presigned 图片 URL → minio:// 稳定引用（读时再签）
            content=stash_media_urls(content),
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


async def _model_supports_vision(
    session: AsyncSession, *, model_id: int | None, model_name: str | None
) -> bool:
    """查模型 capabilities.vision —— 决定是否允许把图片喂给它。"""
    stmt = select(LLMModel).where(LLMModel.deleted_at.is_(None))
    if model_id is not None:
        stmt = stmt.where(LLMModel.id == model_id)
    elif model_name:
        stmt = stmt.where(LLMModel.code == model_name)
    else:
        return False
    row = (await session.execute(stmt)).scalars().first()
    return bool((row.capabilities or {}).get("vision")) if row else False


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


def _clip_citations(citations: list[dict], *, max_items: int = 20) -> list[dict]:
    """retriever 节点输出去 bloat：每条 citation 原文截 300 字预览、列表封顶 max_items。

    原文全量已在 generation 子节点的 messages 里，溯源面板只需预览 + 分项分数。
    """
    out: list[dict] = []
    for c in citations[:max_items]:
        item = {k: v for k, v in c.items() if k != "content"}
        content = c.get("content") or ""
        item["preview"] = content[:300] + "…" if len(content) > 300 else content
        out.append(item)
    return out


async def _inline_image_urls(messages: list[dict]) -> list[dict]:
    """把多模态消息里 image_url 块的本地 url 转 base64 内联（远端可达）。"""
    from chameleon.integrations.mediagen import ensure_fetchable

    out: list[dict] = []
    for m in messages:
        content = m.get("content")
        if not isinstance(content, list):
            out.append(m)
            continue
        blocks = []
        for b in content:
            if isinstance(b, dict) and b.get("type") == "image_url":
                url = (b.get("image_url") or {}).get("url")
                if url:
                    b = {**b, "image_url": {**b["image_url"], "url": await ensure_fetchable(url)}}
            blocks.append(b)
        out.append({**m, "content": blocks})
    return out


def _strip_image_blocks(content: object) -> object:
    """非视觉模型：把多模态 content 摊平成纯文本，丢弃 image/audio 块，避免上游报错。"""
    if not isinstance(content, list):
        return content
    texts = [
        b.get("text", "")
        for b in content
        if isinstance(b, dict) and b.get("type") == "text"
    ]
    joined = "\n".join(t for t in texts if t)
    return joined or "(已忽略图片：该模型不支持视觉，请改用视觉模型)"


def build_messages(
    *,
    system_prompt: str | None,
    kb_context: str,
    messages: list[dict],
    vision: bool = True,
) -> list:
    """把 system + (kb_context 拼到 system 前缀) + 历史 message → LangChain messages。

    vision=False 时剥掉用户消息里的图片块（非视觉模型收到图会报错）。
    """
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
            out.append(HumanMessage(content=content if vision else _strip_image_blocks(content)))
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
    invoke_agent_key: str | None = None,
    gen_params: dict | None = None,
    input_images: list[str] | None = None,
    persist_config: bool = True,
    resume_answer: object = None,
) -> AsyncIterator[dict]:
    """完整 playground 调用编排：绑 key 溯源 → 建/续会话 → KB context → 流式调用。

    invoke_agent_key 非空时走 agent invoke（调该应用 provider，生图/视频/工作流），
    否则 model-direct（直调模型）。会话 / 落库 / trace 机制两者共用。

    溯源（块5）：channel='playground'，落 ChatSession + user/assistant messages +
    call_log 根行（token/cost 从 generation 子行 rollup）。抛 ValidationError /
    BusinessError 由上层 sse_response 兜底成 error chunk。
    """
    if api_key_id is None:
        raise ValidationError(message="Playground 必须绑定一个 Key 用于溯源")

    if invoke_agent_key:
        resolved_model = invoke_agent_key  # 显示 / trace 归属用应用 key
    else:
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
        invoke_agent_key=invoke_agent_key,
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
    fail_msg: str | None = None
    answer_parts: list[str] = []
    try:
        # KB 召回包成 retriever 观测段：record_scope 自身落 retriever 节点（query +
        # citations），且开了嵌套上下文 → build_kb_context 内部的 embedding / reranker
        # 的 record_scope 会以本段为父自动嵌套（解决 embedding 落 trace 根、时长看着
        # 与 retriever 相加的问题）。无 KB 时不开段。
        if invoke_agent_key:
            # 调用应用 provider（生图/视频/工作流等），把 StreamEvent 转 playground chunk
            async for chunk in _stream_agent(
                invoke_agent_key=invoke_agent_key,
                messages=messages,
                session_id=session_id,
                request_id=request_id,
                app_id=PLAYGROUND_APP_ID,
                gen_params=gen_params,
                input_images=input_images,
                resume_answer=resume_answer,
            ):
                if chunk.get("delta"):
                    answer_parts.append(chunk["delta"])
                if chunk.get("error"):
                    # _stream_agent 把 provider 异常转成 error chunk（不上抛），
                    # 这里同步失败标记——否则根 trace 落 success=True 观测失真
                    ok = False
                    err_chunk = chunk["error"]
                    fail_msg = (
                        f"{err_chunk.get('type', 'Error')}: "
                        f"{err_chunk.get('message', '')}"[:500]
                    )
                yield chunk
        else:
            if kb_ids:
                async with record_scope(
                    observation_type=ObservationType.RETRIEVER,
                    name="kb.search",
                    request_payload={
                        "query": user_text[:500],
                        "kb_ids": kb_ids,
                        "top_k": PLAYGROUND_TOP_K,
                    },
                ) as kb_scope:
                    kb_context, citations = await build_kb_context(
                        session, query=user_text, kb_ids=kb_ids
                    )
                    kb_scope.response_payload = {
                        "count": len(citations),
                        "citations": _clip_citations(citations),
                    }
            else:
                kb_context, citations = "", []
            vision_ok = await _model_supports_vision(
                session, model_id=model_id, model_name=model_name
            )
            # 视觉模型：把消息里的本地 MinIO 图 url 转 base64 内联（上游抓不到 localhost）
            msgs = await _inline_image_urls(messages) if vision_ok else messages
            lc_messages = build_messages(
                system_prompt=system_prompt,
                kb_context=kb_context,
                messages=msgs,
                vision=vision_ok,
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
            # 媒体生成无 token rollup → 按绑定生成模型 + 参数算成本（CNY）落 trace
            if invoke_agent_key and ok:
                media_cost, gen_code = await resolve_agent_media_cost(
                    session, agent_key=invoke_agent_key, gen_params=gen_params
                )
                if media_cost is not None:
                    cost = media_cost
                if gen_code:
                    fmodel = gen_code
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
                error_message=fail_msg,
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


async def _stream_agent(
    *,
    invoke_agent_key: str,
    messages: list[dict],
    session_id: str,
    request_id: str,
    app_id: str,
    gen_params: dict | None = None,
    input_images: list[str] | None = None,
    resume_answer: object = None,
) -> AsyncIterator[dict]:
    """调用某应用的 provider（生图/视频/工作流等），把 StreamEvent 转 playground chunk。

    delta（含生图返回的 Markdown 图片 ![](url)）→ {"delta"}；citation → {"citation"}；
    error → {"error"}（终态，其后不再发 end——契约见 core/api/sse_events）；正常
    流末补 {"end": True}（否则前端永远「生成中」）。生成参数 /
    首帧图经 InvokeContext.options 透传给 provider→driver。
    """
    from chameleon.providers.base.registry import AGENTS, PROVIDERS
    from chameleon.providers.base.types import InvokeContext, Message

    agent = AGENTS.get(invoke_agent_key)
    if agent is None:
        # 契约（core/api/sse_events）：error 是终态事件，其后不得再发 end——
        # 否则前端把 failed 冲成 done、失败样式丢失
        yield {"error": {"type": "AgentNotFound", "message": f"应用未注册或未启用: {invoke_agent_key}"}}
        return
    provider = PROVIDERS.get(agent.provider)
    if provider is None:
        yield {"error": {"type": "ProviderError", "message": f"provider 未注册: {agent.provider}"}}
        return

    history = [
        Message(role=m["role"], content=m["content"])
        for m in messages[:-1]
        if m.get("role") in ("user", "assistant")
    ]
    last_content = messages[-1].get("content", "") if messages else ""
    input_val: object = (
        last_content
        if isinstance(last_content, str)
        else [Message(role="user", content=last_content)]
    )
    # durable HITL 续跑：pending 按 durable scope_ref（=会话 session_id）寻址，journal 按首跑 run_id
    # 寻址——两者不同，故服务端按 session_id 读 pending（含 call_index/原始 query/run_id），再用
    # spec.run_id 作 request_id 命中 journal 重放（session_id 即 scope，不变）。评审17 #3：服务端权威读。
    cvars: dict = {}
    eff_session, eff_request = session_id, request_id
    if resume_answer is not None:
        from chameleon.engine.agent.durable import resolve_resume

        spec = await resolve_resume(invoke_agent_key, session_id)
        if spec is None or not spec.run_id:
            yield {"error": {"type": "ResumeError", "message": "无暂停可恢复：该会话无待人工输入"}}
            return
        cvars = {"_resume_call_index": spec.call_index, "_resume_answer": resume_answer}
        eff_request = spec.run_id  # journal 键含首跑 run_id，必须复用才命中重放
        if spec.query is not None:
            input_val = spec.query  # 原始 query 重放（journal 重放 complete 不重调）
    ctx = InvokeContext(
        agent_def=agent,
        input=input_val,
        history=history,
        session_id=eff_session,  # = durable scope_ref，首跑与 resume 一致才命中 pending/journal
        app_id=app_id,
        request_id=eff_request,
        stream=True,
        context_vars=cvars,
        options={"gen_params": gen_params or {}, "input_images": input_images or []},
    )
    # 事件→chunk 走统一转换器（与 embed 共用，新事件只改 stream_translate 一处）
    from chameleon.core.api.stream_translate import (
        StreamTranslateState,
        translate_event,
    )

    st = StreamTranslateState()
    try:
        async for ev in provider.stream(ctx):
            for chunk in translate_event(ev, st):
                yield chunk
            if st.saw_error:
                return  # error 终态：不再发 end（契约见 sse_events）
    except Exception as e:  # noqa: BLE001
        logger.exception("playground agent invoke failed | agent=%s", invoke_agent_key)
        yield {"error": {"type": type(e).__name__, "message": str(e)[:300]}}
        return
    usage_sse = st.usage_sse()
    yield {"end": True, **({"usage": usage_sse} if usage_sse else {})}


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


def _build_rewrite_prompt(
    current_prompt: str, answer: str, instruction: str
) -> str:
    """组装「基于回答改写 System Prompt」的 LLM 提示词（强约束只回纯文本）。"""
    base = current_prompt.strip() or "（当前没有 System Prompt）"
    return (
        "你是提示词工程助手。下面给你三样东西：\n"
        "1) 当前的 System Prompt\n"
        "2) 在该 System Prompt 下，模型对某次提问产出的一条不理想回答\n"
        "3) 用户对回答的改写诉求\n\n"
        "请基于这三者，改写出一个更好的 System Prompt，使模型按用户诉求作答。\n"
        f"=== 当前 System Prompt ===\n{base}\n\n"
        f"=== 这条不理想的模型回答 ===\n{answer.strip()}\n\n"
        f"=== 用户的改写诉求 ===\n{instruction.strip()}\n\n"
        "只输出改写后的完整 System Prompt 纯文本，"
        "不要任何解释、前后缀、Markdown 代码块或 JSON 包裹。"
    )


async def rewrite_prompt(
    session: AsyncSession,
    *,
    current_prompt: str,
    answer: str,
    instruction: str,
    model_code: str | None = None,
) -> str:
    """单条/即时改写 System Prompt：当前 prompt + 一条回答 + 改写诉求 → 新 prompt 纯文本。

    与 H3 optimizer（datasets/optimizer.py）的本质区分——别混淆：
    - H1 rewrite（此处）：单条 / 即时 / 零数据集上下文 / 单次 LLM 调用 / 不落任何库，
      结果直接回灌前端 ParamPanel。
    - H3 optimizer：run 级 / 汇总整集低分样本共性缺陷 / 重型 / 落库版本链。
    两者各自独立 service、不互相 import，仅共享 channel='eval' 的 TraceContext 范式。

    Args:
        session: DB 会话（仅满足 service 边界签名，本函数不落库）。
        current_prompt: 当前 System Prompt（可空）。
        answer: 触发改写的那条不理想模型回答。
        instruction: 用户的改写诉求（非空）。
        model_code: 指定改写用模型 code；None 走系统默认 chat 模型。

    Returns:
        改写后的完整 System Prompt 纯文本（已 strip）。

    Raises:
        BusinessError: LLM 返回空内容。
    """
    from chameleon.aikit import LLMRunner

    prompt = _build_rewrite_prompt(current_prompt, answer, instruction)

    raw = await LLMRunner.run_text(
        prompt,
        model=model_code,
        channel=Channel.EVAL.value,
        app_id=EVAL_APP_ID,
        session_id=f"eval-rewrite-{uuid.uuid4().hex[:8]}",
        retries=0,
    )

    rewritten = str(raw).strip()
    if not rewritten:
        raise BusinessError(
            ResultCode.Fail, message="改写失败，请调整需求后重试"
        )
    return rewritten
