"""agent 业务编排服务

非流路径 9 步（设计文档 S4.3 ①-⑨）：
  ① 注册表查询
  ② 会话处理（创建 or 拿已有）
  ③ 历史装载（str → 取 session；list → 客户端自管，不取）
  ④ 落库 user msg（先写防丢）
  ⑤ 装 InvokeContext
  ⑥ 调 provider.invoke
  ⑦ 落库 assistant msg
  ⑧ touch 会话（last_message_at / title / provider_conv_id）
  ⑨ 审计 call_log
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from typing import Any

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.api.agent.schemas import (
    AgentItem,
    InvokeRequest,
    InvokeResponse,
)
from chameleon.api.sessions import service as session_service
from chameleon.api.sessions.schemas import AppendMessageDraft
from chameleon.core.api.exceptions import (
    AgentNotFoundError,
    BusinessError,
    ProviderError,
    ResultCode,
)
from chameleon.core.infra.auth import CurrentApp
from chameleon.core.infra.db import AsyncSessionLocal
from chameleon.core.observe import (
    TraceContext,
    reset_trace_context,
    set_trace_context,
)
from chameleon.core.utils.spans import SpanRecorder
from chameleon.providers.base import AGENTS, PROVIDERS
from chameleon.providers.base.types import (
    AgentDef,
    AudioUrlBlock,
    ContentBlock,
    ImageUrlBlock,
    InvokeContext,
    StreamEvent,
    StreamEventType,
    TextBlock,
    _StreamAggregator,
)
from chameleon.providers.base.types import Message as ProviderMessage
from chameleon.system.api_key import service as api_key_service

# ── agent 列表 / 详情（注册表只读访问） ──────────────────


def list_agents() -> list[AgentItem]:
    return [
        AgentItem(
            key=a.key,
            provider=a.provider,
            description=a.description,
            version=a.version,
            tags=list(a.tags),
        )
        for a in AGENTS.values()
    ]


def get_agent(key: str) -> AgentItem:
    ad = AGENTS.get(key)
    if ad is None:
        raise AgentNotFoundError(message=f"agent 不存在: {key}")
    return AgentItem(
        key=ad.key,
        provider=ad.provider,
        description=ad.description,
        version=ad.version,
        tags=list(ad.tags),
    )


# ── 非流式 invoke 主流程 ────────────────────────────────


# ── Attachments (Phase A) ─────────────────────────────────
# 把 attachments 翻译成 ContentBlock 列表。仅图/音走多模态；其他类型 Phase A
# 暂未实现（PDF/CSV 等会随 Phase B 临时 RAG 上线）。


def blocks_from_attachments(
    user_text: str,
    attachments: list[dict[str, Any]] | None,
) -> list[ContentBlock] | None:
    """attachments + text → ContentBlock 列表。无附件返 None（调用方走 str 流程）。

    Raises:
        BusinessError(NotImplemented): 出现 Phase A 尚未支持的 mime 类型
    """
    if not attachments:
        return None
    blocks: list[ContentBlock] = [TextBlock(text=user_text)] if user_text else []
    for att in attachments:
        url = att.get("object_url")
        mime = (att.get("mime") or "").lower()
        if not url:
            continue
        if mime.startswith("image/"):
            blocks.append(ImageUrlBlock(image_url={"url": url}))
        elif mime.startswith("audio/"):
            blocks.append(AudioUrlBlock(audio_url={"url": url}))
        else:
            # PDF / CSV / DOCX 等：Phase B 临时 RAG 才接，Phase A 显式不静默丢
            raise BusinessError(
                ResultCode.NotImplemented,
                message=f"暂不支持文件类型 {mime}（仅图片 / 音频）—— 文档与数据文件将随 Phase B 上线",
            )
    return blocks or None


def _apply_attachments(
    req: InvokeRequest,
    current_input_text: str,
    current_input_obj,
) -> tuple[object, list[dict[str, Any]] | None]:
    """合并 attachments 到 current_input：

    - 没附件 → 原样
    - input 是 str 且有附件 → 转 list[ProviderMessage] 单元素，content 是 ContentBlock 列表
    - input 是 list[ProviderMessage] 且有附件 → 把附件 blocks merge 到最后一条 user 上
    返回 (new_input_obj, blocks_for_persistence)
    """
    attachments = (
        [a.model_dump() if hasattr(a, "model_dump") else a for a in req.attachments]
        if req.attachments
        else None
    )
    if not attachments:
        return current_input_obj, None

    blocks = blocks_from_attachments(current_input_text, attachments)
    if blocks is None:
        return current_input_obj, None

    if isinstance(current_input_obj, str):
        new_obj = [ProviderMessage(role="user", content=blocks)]
    else:
        # list[ProviderMessage]：把 blocks 设到最后一条
        last = current_input_obj[-1]
        new_obj = list(current_input_obj[:-1]) + [
            ProviderMessage(
                role=last.role,
                content=blocks,
                name=last.name,
                tool_call_id=last.tool_call_id,
            )
        ]
    return new_obj, [b.model_dump() for b in blocks]


def _assert_agent_scope(current_app: CurrentApp, agent_key: str) -> None:
    """智能体级密钥只能调用其绑定的 agent；global 作用域密钥放行。

    invoke / stream_invoke 共用入口，覆盖 /v1/invoke 与 /v1/chat/completions。
    作用域域名为 "app"（智能体已升格为「应用」），scope_ref = agent_key。
    """
    from chameleon.core.infra.auth import assert_scope

    assert_scope(current_app, "app", agent_key)


async def invoke(
    session: AsyncSession,
    agent_key: str,
    req: InvokeRequest,
    *,
    current_app: CurrentApp,
    request_id: str,
    channel: str = "api",
) -> InvokeResponse:
    _assert_agent_scope(current_app, agent_key)
    start_ts = time.monotonic()
    rec = SpanRecorder()

    # ① 注册表查询
    with rec.span("agent_resolve", meta={"agent_key": agent_key}):
        agent_def = AGENTS.get(agent_key)
        if agent_def is None:
            raise AgentNotFoundError(message=f"agent 不存在: {agent_key}")
        provider = PROVIDERS.get(agent_def.provider)
        if provider is None:
            # 理论上 init_registry 已经 fail-fast 保证，这里兜底
            raise BusinessError(
                ResultCode.RegistryError,
                message=f"provider 未注册: {agent_def.provider}",
            )

    # ② 会话处理（带终端用户身份）
    with rec.span("conversation_setup"):
        conv = await _ensure_session(
            session,
            agent_def,
            req.session_id,
            current_app=current_app,
            end_user_id=req.user,
        )

    # S8：set TraceContext —— 其后所有 LLM 调用经 BaseLLM 回调自动落 generation 行。
    # 不用 try/finally：ContextVar 随 asyncio task 生命周期自然回收（一请求一 task）。
    _api_key_id_trace = (
        current_app.id if "admin" not in current_app.scopes else None
    )
    set_trace_context(
        TraceContext(
            request_id=request_id,
            channel=channel,
            app_id=current_app.app_id,
            api_key_id=_api_key_id_trace,
            agent_key=agent_key,
            session_id=conv.session_id,
            end_user_id=conv.end_user_id,
        )
    )

    # ③ 历史装载（A10 裁决）
    if isinstance(req.input, str):
        history = await session_service.load_messages(session, conv.session_id)
        current_input_text = req.input
        current_input_obj = req.input  # provider 端用 str
    else:
        # list[MessageInput]
        if not req.input:
            raise BusinessError(
                ResultCode.ValidationError, message="input 列表不能为空"
            )
        if req.input[-1].role != "user":
            raise BusinessError(
                ResultCode.ValidationError,
                message="input 列表最后一条必须是 user",
            )
        history = []  # A10：client 自管历史，service 不消费 session 历史
        current_input_text = req.input[-1].content
        current_input_obj = [
            ProviderMessage(
                role=m.role,
                content=m.content,
                name=m.name,
                tool_call_id=m.tool_call_id,
            )
            for m in req.input
        ]

    # 附件 → ContentBlock（Phase A 仅图/音；其他类型 raise NotImplemented）
    current_input_obj, persist_blocks = _apply_attachments(
        req, current_input_text, current_input_obj
    )

    # ④ 落库 user msg（先写防丢；list 模式只落 last user，不落 client 自管历史）
    with rec.span("history_persist"):
        await session_service.append(
            session,
            conv.session_id,
            AppendMessageDraft(
                role="user",
                content=current_input_text,
                content_blocks=persist_blocks,
                provider=agent_def.provider,
                end_user_id=conv.end_user_id,
            ),
        )

    # ⑤ 装 InvokeContext
    ctx = InvokeContext(
        agent_def=agent_def,
        input=current_input_obj,
        history=history,
        session_id=conv.session_id,
        provider_conv_id=conv.provider_conv_id,
        context_vars=req.context,
        options=req.options,
        app_id=current_app.app_id,
        stream=False,
        request_id=request_id,
    )

    # ⑥ 调 provider（非流式聚合）
    success = True
    code = ResultCode.Success.value
    err_msg: str | None = None
    request_payload = _build_request_payload(req, agent_def, current_input_text)
    try:
        with rec.span("provider_invoke", meta={"provider": agent_def.provider}):
            result = await provider.invoke(ctx)
    except ProviderError as pe:
        success = False
        code = int(pe.code)
        err_msg = pe.message
        await _record_call(
            session,
            request_id=request_id,
            app_id=current_app.app_id,
            agent_key=agent_key,
            session_id=conv.session_id,
            stream=False,
            success=False,
            code=code,
            error_message=err_msg,
            duration_ms=int((time.monotonic() - start_ts) * 1000),
            spans=rec.dump(),
            request_payload=request_payload,
            channel=channel,
            observation_type="trace",
            api_key_id=_api_key_id_trace,
            end_user_id=conv.end_user_id,
        )
        raise
    except Exception:
        await _record_call(
            session,
            request_id=request_id,
            app_id=current_app.app_id,
            agent_key=agent_key,
            session_id=conv.session_id,
            stream=False,
            success=False,
            code=ResultCode.InternalError.value,
            error_message="unexpected error",
            duration_ms=int((time.monotonic() - start_ts) * 1000),
            spans=rec.dump(),
            request_payload=request_payload,
            channel=channel,
            observation_type="trace",
            api_key_id=_api_key_id_trace,
            end_user_id=conv.end_user_id,
        )
        raise

    # ⑦ 落库 assistant msg + ⑧ touch
    with rec.span("response_persist"):
        await session_service.append(
            session,
            conv.session_id,
            AppendMessageDraft(
                role="assistant",
                content=result.answer,
                steps=[s.model_dump() for s in result.steps] or None,
                citations=[c.model_dump() for c in result.citations] or None,
                tool_calls=[tc.model_dump() for tc in result.tool_calls] or None,
                usage=result.usage.model_dump() if result.usage else None,
                provider=agent_def.provider,
                end_user_id=conv.end_user_id,
            ),
        )
        title = current_input_text if conv.title is None else None
        await session_service.touch(
            session,
            conv.session_id,
            title=title,
            provider_conv_id=result.provider_conv_id,
        )

    # 兜底填 usage：provider 自身没透出（如图引擎下多 LLM 节点）时，从
    # BaseLLM 回调写下的 generation 子行聚合补回；不影响 provider 已给 usage 的情况。
    if result.usage is None:
        from chameleon.providers.base.types import Usage

        p, c, t = await api_key_service.aggregate_generation_usage(
            session, request_id
        )
        if any(v is not None for v in (p, c, t)):
            result.usage = Usage(
                prompt_tokens=p, completion_tokens=c, total_tokens=t
            )

    # ⑨ 审计（root trace 行 —— generation 子行由 BaseLLM 回调自动落）
    usage = result.usage
    response_payload = _build_response_payload(result)
    await _record_call(
        session,
        request_id=request_id,
        app_id=current_app.app_id,
        agent_key=agent_key,
        session_id=conv.session_id,
        stream=False,
        success=success,
        code=code,
        error_message=err_msg,
        duration_ms=int((time.monotonic() - start_ts) * 1000),
        prompt_tokens=usage.prompt_tokens if usage else None,
        completion_tokens=usage.completion_tokens if usage else None,
        total_tokens=usage.total_tokens if usage else None,
        spans=rec.dump(),
        request_payload=request_payload,
        response_payload=response_payload,
        channel=channel,
        observation_type="trace",
        api_key_id=_api_key_id_trace,
        end_user_id=conv.end_user_id,
    )

    return InvokeResponse(
        session_id=conv.session_id,
        request_id=request_id,
        answer=result.answer,
        steps=result.steps,
        citations=result.citations,
        tool_calls=result.tool_calls,
        usage=result.usage,
    )


# ── helpers ─────────────────────────────────────────────


async def _ensure_session(
    session: AsyncSession,
    agent_def: AgentDef,
    given_session_id: str | None,
    *,
    current_app: CurrentApp,
    end_user_id: str | None = None,
):
    """缺省 → 新建；否则取并校验权限 + agent + 终端用户一致性

    S3 重构：新建会话时盖章 owner api_key_id（admin 走 JWT 时为 None）+ end_user_id；
    续接已有会话时校验终端用户一致性（防止跨用户访问同 session_id）。
    """
    # admin JWT 路径 id=0（哨兵），不是真实 api_key FK；置 None 避免 FK 失败
    api_key_id = current_app.id if "admin" not in current_app.scopes else None

    if not given_session_id:
        return await session_service.create(
            session,
            agent_key=agent_def.key,
            app_id=current_app.app_id,
            end_user_id=end_user_id,
            api_key_id=api_key_id,
        )

    conv = await session_service.get(session, given_session_id, current_app=current_app)
    # agent 一致性：同一 session 不允许切换 agent
    if conv.agent_key != agent_def.key:
        raise BusinessError(
            ResultCode.SessionIdInvalid,
            message=(
                f"session_id 已绑定 agent={conv.agent_key}，"
                f"不可用于调用 agent={agent_def.key}"
            ),
        )
    # 终端用户一致性：会话已绑定终端用户时，必须匹配（防越权）
    if (
        end_user_id is not None
        and conv.end_user_id is not None
        and conv.end_user_id != end_user_id
    ):
        raise BusinessError(
            ResultCode.SessionIdInvalid,
            message="session_id 已绑定其他终端用户，不可跨用户访问",
        )
    return conv


async def _record_call(session: AsyncSession, **kwargs) -> None:
    """写 call_log；失败仅 warn，不阻塞响应"""
    try:
        await api_key_service.record_call(session, **kwargs)
    except Exception:  # noqa: BLE001
        logger.warning(
            "call_log write failed | request_id={}", kwargs.get("request_id")
        )


def _build_request_payload(
    req: InvokeRequest, agent_def: AgentDef, current_input_text: str
) -> dict:
    """构造入参快照（不暴露 raw bytes / 大对象，限制长度避免 JSONB 爆）"""
    return {
        "agent": agent_def.key,
        "provider": agent_def.provider,
        "session_id": req.session_id,
        "input_preview": (
            current_input_text[:2000] if isinstance(current_input_text, str) else None
        ),
        "input_kind": "string" if isinstance(req.input, str) else "list",
        "context": req.context or None,
        "options": req.options or None,
    }


def _build_response_payload(result) -> dict:
    answer = (result.answer or "")[:4000]
    return {
        "answer_preview": answer,
        "steps": [s.model_dump() for s in result.steps] or None,
        "citations": [c.model_dump() for c in result.citations] or None,
        "tool_calls": [tc.model_dump() for tc in result.tool_calls] or None,
        "usage": result.usage.model_dump() if result.usage else None,
    }


# ── 流式 invoke 主流程 ────────────────────────────────


async def stream_invoke(
    agent_key: str,
    req: InvokeRequest,
    *,
    current_app: CurrentApp,
    request_id: str,
    channel: str = "api",
) -> AsyncIterator[StreamEvent]:
    """流式编排：边流边落库

    ★ 自管 session（不复用 FastAPI Depends 的）——StreamingResponse 期间
      Depends session 已结束生命周期。

    A3 裁决：
    - 流中 provider 抛错 → emit error event，不落 assistant msg
    - 客户端断开（CancelledError）→ 静默退出，不落 assistant msg；call_log 记 failed
    - 正常完成 → 落 assistant msg、touch 会话、写 call_log（success）
    """
    _assert_agent_scope(current_app, agent_key)
    start_ts = time.monotonic()
    rec = SpanRecorder()

    # 共享准备阶段（① 注册表 / ② 会话 / ③ 历史 / ④ 落 user msg）
    with rec.span("prepare_invocation"):
        async with AsyncSessionLocal() as session:
            prep = await _prepare_invocation(
                session,
                agent_key,
                req,
                current_app=current_app,
                request_id=request_id,
                stream=True,
            )
            await session.commit()
    agent_def, provider, conv, ctx, current_input_text = prep
    request_payload = _build_request_payload(req, agent_def, current_input_text)

    # S8：set TraceContext —— 流期间任何 LLM 调用走 BaseLLM 回调自动落 generation
    _api_key_id_trace = (
        current_app.id if "admin" not in current_app.scopes else None
    )
    set_trace_context(
        TraceContext(
            request_id=request_id,
            channel=channel,
            app_id=current_app.app_id,
            api_key_id=_api_key_id_trace,
            agent_key=agent_key,
            session_id=conv.session_id,
            end_user_id=conv.end_user_id,
        )
    )

    # 流式调用 + 聚合器
    aggregator = _StreamAggregator(session_id=ctx.session_id, request_id=request_id)
    failed = False
    fail_code: int = ResultCode.Success.value
    fail_msg: str | None = None
    provider_span_start = rec.now_ms()

    try:
        async for event in provider.stream(ctx):
            if event.type == StreamEventType.error:
                failed = True
                fail_code = int(
                    event.data.get("code") or ResultCode.ProviderInternalError
                )
                fail_msg = event.data.get("message", "provider stream error")
                yield event
                # error 后停止读 provider
                break
            if event.type == StreamEventType.done:
                # 截胡 provider 的 done —— service 层最后统一 emit 完整版
                aggregator.feed(event)
                continue
            aggregator.feed(event)
            yield event

        # 正常完成 → emit service 增强后的 done 事件（含 session_id 等）
        if not failed:
            final_result = aggregator.result()
            yield StreamEvent(
                type=StreamEventType.done,
                data=final_result.model_dump(exclude_none=True),
            )
    except ProviderError as pe:
        failed = True
        fail_code = int(pe.code)
        fail_msg = pe.message
        # 向客户端推一条 error event
        yield StreamEvent(
            type=StreamEventType.error,
            data={"code": fail_code, "message": fail_msg},
        )
    except Exception:  # noqa: BLE001
        failed = True
        fail_code = ResultCode.InternalError.value
        fail_msg = "unexpected error"
        logger.exception(
            "stream_invoke unexpected error | agent={} | session={}",
            agent_key,
            ctx.session_id,
        )
        yield StreamEvent(
            type=StreamEventType.error,
            data={"code": fail_code, "message": fail_msg},
        )
    finally:
        # 收口 provider_invoke span
        rec.add(
            "provider_invoke",
            start_ms=provider_span_start,
            end_ms=rec.now_ms(),
            status="failed" if failed else "success",
            meta={"provider": agent_def.provider, "stream": True},
            error_message=fail_msg if failed else None,
        )
        # 后置写入 + 审计（独立 session）
        await _stream_finalize(
            failed=failed,
            fail_code=fail_code,
            fail_msg=fail_msg,
            agent_def=agent_def,
            conv_session_id=ctx.session_id,
            conv_had_title=conv.title is not None,
            conv_end_user_id=conv.end_user_id,
            current_input_text=current_input_text,
            aggregator=aggregator,
            current_app=current_app,
            agent_key=agent_key,
            request_id=request_id,
            channel=channel,
            duration_ms=int((time.monotonic() - start_ts) * 1000),
            spans=rec,
            request_payload=request_payload,
        )


async def _prepare_invocation(
    session: AsyncSession,
    agent_key: str,
    req: InvokeRequest,
    *,
    current_app: CurrentApp,
    request_id: str,
    stream: bool,
):
    """① 注册表 / ② 会话 / ③ 历史 / ④ 落 user msg（流式与非流式共享）"""
    _ = request_id  # 由调用方独立使用
    agent_def = AGENTS.get(agent_key)
    if agent_def is None:
        raise AgentNotFoundError(message=f"agent 不存在: {agent_key}")
    provider = PROVIDERS.get(agent_def.provider)
    if provider is None:
        raise BusinessError(
            ResultCode.RegistryError,
            message=f"provider 未注册: {agent_def.provider}",
        )

    conv = await _ensure_session(
        session,
        agent_def,
        req.session_id,
        current_app=current_app,
        end_user_id=req.user,
    )

    if isinstance(req.input, str):
        history = await session_service.load_messages(session, conv.session_id)
        current_input_text = req.input
        current_input_obj = req.input
    else:
        if not req.input:
            raise BusinessError(
                ResultCode.ValidationError, message="input 列表不能为空"
            )
        if req.input[-1].role != "user":
            raise BusinessError(
                ResultCode.ValidationError,
                message="input 列表最后一条必须是 user",
            )
        history = []
        current_input_text = req.input[-1].content
        current_input_obj = [
            ProviderMessage(
                role=m.role,
                content=m.content,
                name=m.name,
                tool_call_id=m.tool_call_id,
            )
            for m in req.input
        ]

    # 附件 → ContentBlock（Phase A 仅图/音；其他类型 raise NotImplemented）
    current_input_obj, persist_blocks = _apply_attachments(
        req, current_input_text, current_input_obj
    )

    await session_service.append(
        session,
        conv.session_id,
        AppendMessageDraft(
            role="user",
            content=current_input_text,
            content_blocks=persist_blocks,
            provider=agent_def.provider,
            end_user_id=conv.end_user_id,
        ),
    )

    ctx = InvokeContext(
        agent_def=agent_def,
        input=current_input_obj,
        history=history,
        session_id=conv.session_id,
        provider_conv_id=conv.provider_conv_id,
        context_vars=req.context,
        options=req.options,
        app_id=current_app.app_id,
        stream=stream,
        request_id=request_id,
    )
    return agent_def, provider, conv, ctx, current_input_text


async def _stream_finalize(
    *,
    failed: bool,
    fail_code: int,
    fail_msg: str | None,
    agent_def: AgentDef,
    conv_session_id: str,
    conv_had_title: bool,
    conv_end_user_id: str | None,
    current_input_text: str,
    aggregator: _StreamAggregator,
    current_app: CurrentApp,
    agent_key: str,
    request_id: str,
    channel: str = "api",
    duration_ms: int,
    spans: SpanRecorder,
    request_payload: dict,
) -> None:
    """流结束后：落 assistant msg + touch + call_log（独立 session 防 yield 期间 session 已死）

    A3：failed → 仅写 call_log；成功 → 写 assistant + touch + call_log
    """
    result = aggregator.result()
    async with AsyncSessionLocal() as session:
        try:
            if not failed and result.answer:
                with spans.span("response_persist"):
                    await session_service.append(
                        session,
                        conv_session_id,
                        AppendMessageDraft(
                            role="assistant",
                            content=result.answer,
                            steps=[s.model_dump() for s in result.steps] or None,
                            citations=[c.model_dump() for c in result.citations]
                            or None,
                            tool_calls=[tc.model_dump() for tc in result.tool_calls]
                            or None,
                            usage=result.usage.model_dump() if result.usage else None,
                            end_user_id=conv_end_user_id,
                            provider=agent_def.provider,
                        ),
                    )
                    title = current_input_text if not conv_had_title else None
                    await session_service.touch(
                        session,
                        conv_session_id,
                        title=title,
                        provider_conv_id=result.provider_conv_id,
                    )

            # 兜底填 usage：provider 没透出 usage 时，从 generation 子行聚合
            if result.usage is None and not failed:
                from chameleon.providers.base.types import Usage

                p, c, t = await api_key_service.aggregate_generation_usage(
                    session, request_id
                )
                if any(v is not None for v in (p, c, t)):
                    result.usage = Usage(
                        prompt_tokens=p, completion_tokens=c, total_tokens=t
                    )
            usage = result.usage
            response_payload = (
                _build_response_payload(result)
                if (not failed and result.answer)
                else None
            )
            _api_key_id_finalize = (
                current_app.id if "admin" not in current_app.scopes else None
            )
            await _record_call(
                session,
                request_id=request_id,
                app_id=current_app.app_id,
                agent_key=agent_key,
                session_id=conv_session_id,
                stream=True,
                channel=channel,
                success=not failed,
                code=fail_code if failed else ResultCode.Success.value,
                error_message=fail_msg,
                duration_ms=duration_ms,
                prompt_tokens=usage.prompt_tokens if usage else None,
                completion_tokens=usage.completion_tokens if usage else None,
                total_tokens=usage.total_tokens if usage else None,
                spans=spans.dump(),
                request_payload=request_payload,
                response_payload=response_payload,
                observation_type="trace",
                api_key_id=_api_key_id_finalize,
                end_user_id=conv_end_user_id,
            )
            await session.commit()
        except Exception:  # noqa: BLE001
            logger.exception("stream_finalize write failed | request_id={}", request_id)
            await session.rollback()
