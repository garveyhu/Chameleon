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

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.api.agent.schemas import (
    AgentItem,
    InvokeRequest,
    InvokeResponse,
)
from chameleon.system.api_key import service as api_key_service
from chameleon.api.conversation import service as conv_service
from chameleon.api.conversation.schemas import AppendMessageDraft
from chameleon.core.infra.auth import CurrentApp
from chameleon.core.infra.db import AsyncSessionLocal
from chameleon.core.api.exceptions import (
    AgentNotFoundError,
    BusinessError,
    ProviderError,
    ResultCode,
)
from chameleon.core.utils.spans import SpanRecorder
from chameleon.providers.base import AGENTS, PROVIDERS
from chameleon.providers.base.types import (
    AgentDef,
    InvokeContext,
    StreamEvent,
    StreamEventType,
    _StreamAggregator,
)
from chameleon.providers.base.types import Message as ProviderMessage

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


async def invoke(
    session: AsyncSession,
    agent_key: str,
    req: InvokeRequest,
    *,
    current_app: CurrentApp,
    request_id: str,
) -> InvokeResponse:
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

    # ② 会话处理
    with rec.span("conversation_setup"):
        conv = await _ensure_conversation(
            session,
            agent_def,
            req.session_id,
            current_app=current_app,
        )

    # ③ 历史装载（A10 裁决）
    if isinstance(req.input, str):
        history = await conv_service.load_messages(session, conv.session_id)
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

    # ④ 落库 user msg（先写防丢；list 模式只落 last user，不落 client 自管历史）
    with rec.span("history_persist"):
        await conv_service.append(
            session,
            conv.session_id,
            AppendMessageDraft(
                role="user",
                content=current_input_text,
                provider=agent_def.provider,
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
        )
        raise

    # ⑦ 落库 assistant msg + ⑧ touch
    with rec.span("response_persist"):
        await conv_service.append(
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
            ),
        )
        title = current_input_text if conv.title is None else None
        await conv_service.touch(
            session,
            conv.session_id,
            title=title,
            provider_conv_id=result.provider_conv_id,
        )

    # ⑨ 审计
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


async def _ensure_conversation(
    session: AsyncSession,
    agent_def: AgentDef,
    given_session_id: str | None,
    *,
    current_app: CurrentApp,
):
    """缺省 → 新建；否则取并校验权限 + agent 一致性"""
    if not given_session_id:
        return await conv_service.create(
            session,
            agent_key=agent_def.key,
            provider=agent_def.provider,
            app_id=current_app.app_id,
        )

    conv = await conv_service.get(session, given_session_id, current_app=current_app)
    # agent 一致性：同一 session 不允许切换 agent
    if conv.agent_key != agent_def.key:
        raise BusinessError(
            ResultCode.SessionIdInvalid,
            message=(
                f"session_id 已绑定 agent={conv.agent_key}，"
                f"不可用于调用 agent={agent_def.key}"
            ),
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
            current_input_text[:2000]
            if isinstance(current_input_text, str)
            else None
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
) -> AsyncIterator[StreamEvent]:
    """流式编排：边流边落库

    ★ 自管 session（不复用 FastAPI Depends 的）——StreamingResponse 期间
      Depends session 已结束生命周期。

    A3 裁决：
    - 流中 provider 抛错 → emit error event，不落 assistant msg
    - 客户端断开（CancelledError）→ 静默退出，不落 assistant msg；call_log 记 failed
    - 正常完成 → 落 assistant msg、touch 会话、写 call_log（success）
    """
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
            current_input_text=current_input_text,
            aggregator=aggregator,
            current_app=current_app,
            agent_key=agent_key,
            request_id=request_id,
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

    conv = await _ensure_conversation(
        session,
        agent_def,
        req.session_id,
        current_app=current_app,
    )

    if isinstance(req.input, str):
        history = await conv_service.load_messages(session, conv.session_id)
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

    await conv_service.append(
        session,
        conv.session_id,
        AppendMessageDraft(
            role="user",
            content=current_input_text,
            provider=agent_def.provider,
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
    current_input_text: str,
    aggregator: _StreamAggregator,
    current_app: CurrentApp,
    agent_key: str,
    request_id: str,
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
                    await conv_service.append(
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
                            provider=agent_def.provider,
                        ),
                    )
                    title = current_input_text if not conv_had_title else None
                    await conv_service.touch(
                        session,
                        conv_session_id,
                        title=title,
                        provider_conv_id=result.provider_conv_id,
                    )

            usage = result.usage
            response_payload = (
                _build_response_payload(result)
                if (not failed and result.answer)
                else None
            )
            await _record_call(
                session,
                request_id=request_id,
                app_id=current_app.app_id,
                agent_key=agent_key,
                session_id=conv_session_id,
                stream=True,
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
            )
            await session.commit()
        except Exception:  # noqa: BLE001
            logger.exception("stream_finalize write failed | request_id={}", request_id)
            await session.rollback()
