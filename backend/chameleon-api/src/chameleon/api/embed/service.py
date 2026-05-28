"""嵌入式调用 service —— 非流 / 流式两条路径，都写 call_logs

API 层只做 DTO 桥接，业务编排在这里。
"""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import hashlib

import jwt
from pydantic import ValidationError as PydanticValidationError

from chameleon.api.embed import session as embed_session
from chameleon.api.embed.schemas import CreateSessionRequest, SessionPolicy
from chameleon.api.sessions import service as session_service
from chameleon.api.sessions.schemas import AppendMessageDraft
from chameleon.core.api.exceptions import (
    BusinessError,
    PermissionDeniedError,
    ResultCode,
    ValidationError,
)
from chameleon.core.api.sse_events import (
    UsagePayload,
    event_citation,
    event_delta,
    event_end,
    event_error,
    event_meta,
)
from chameleon.core.models import Agent, ChatSession, EmbedConfig
from chameleon.core.observe import TraceContext, set_trace_context
from chameleon.core.utils.crypto import get_or_decrypt
from chameleon.providers.base import AGENTS, PROVIDERS
from chameleon.providers.base.errors import ProviderError
from chameleon.providers.base.types import (
    InvokeContext,
    InvokeResult,
    StreamEventType,
    _StreamAggregator,
)
from chameleon.system.api_key.service import record_call


def check_origin(allowed: list | None, origin: str | None) -> None:
    """同源 / 服务端调用允许；allowed 含 "*" 视为公开（任意 origin）；其余须在白名单。"""
    if origin is None:
        return
    if not allowed:
        raise PermissionDeniedError(message="该 embed 未配置 allowed_origins")
    if "*" in allowed:
        return
    if origin not in allowed:
        raise PermissionDeniedError(message=f"origin 不在白名单: {origin}")


async def resolve_embed(session: AsyncSession, embed_key: str) -> EmbedConfig:
    e = (
        await session.execute(
            select(EmbedConfig).where(
                EmbedConfig.embed_key == embed_key,
                EmbedConfig.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if e is None:
        raise BusinessError(
            ResultCode.AgentNotFound, message=f"embed 不存在: {embed_key}"
        )
    if not e.enabled:
        raise ValidationError(message="embed 已禁用")
    return e


async def _resolve_agent(session: AsyncSession, embed: EmbedConfig) -> Agent:
    agent = (
        await session.execute(
            select(Agent).where(
                Agent.id == embed.agent_id, Agent.deleted_at.is_(None)
            )
        )
    ).scalar_one_or_none()
    if agent is None or not agent.enabled:
        raise ValidationError(message="关联 agent 不存在或已禁用")
    if agent.agent_key not in AGENTS:
        raise BusinessError(
            ResultCode.RegistryError,
            message=f"agent {agent.agent_key} 不在 registry，需 reload",
        )
    return agent


def _embed_app_label(embed: EmbedConfig) -> str:
    """embed 发起的调用，call_logs.app_id 用 embed_key 派生的来源标签（不再查 apps 表）。"""
    return f"embed:{embed.embed_key}"


# ── S10：session_policy + 三种身份识别模式 ─────────────────


def _resolve_session_policy(embed: EmbedConfig) -> SessionPolicy:
    """从 embed.session_policy JSON 解析；老 embed 缺字段时返默认（匿名设备）。"""
    raw = embed.session_policy or {}
    try:
        return SessionPolicy(**raw)
    except PydanticValidationError:
        logger.warning(
            "embed session_policy 解析失败，回退默认 | embed_key={}", embed.embed_key
        )
        return SessionPolicy()


def _hash_device_id(device_id: str) -> str:
    """匿名设备模式：sha256 device_id 当 end_user_id（避免存原始浏览器指纹）"""
    return "anon_" + hashlib.sha256(device_id.encode("utf-8")).hexdigest()[:24]


def _verify_jwt_and_extract_sub(policy: SessionPolicy, token: str) -> str:
    """signed_jwt 模式：用 policy 配置的 HS256 共享密钥验签，取 sub claim 作 end_user_id"""
    if not policy.jwt_signing_secret_encrypted:
        raise BusinessError(
            ResultCode.JwtInvalid,
            message="该 embed 未配置 jwt_signing_secret，无法 signed_jwt 模式",
        )
    secret = get_or_decrypt(policy.jwt_signing_secret_encrypted)
    if not secret:
        raise BusinessError(ResultCode.JwtInvalid, message="jwt 密钥解密失败")
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError as e:
        raise BusinessError(ResultCode.JwtInvalid, message="jwt 已过期") from e
    except jwt.InvalidTokenError as e:
        raise BusinessError(ResultCode.JwtInvalid, message="jwt 无效") from e
    sub = payload.get("sub")
    if not sub:
        raise BusinessError(ResultCode.JwtInvalid, message="jwt 缺 sub claim")
    return str(sub)


def resolve_end_user_from_request(
    embed: EmbedConfig, req: CreateSessionRequest
) -> str | None:
    """按 embed 的 session_policy.identification_mode 解析终端用户 id

    - anonymous_device → hash(device_id)
    - external_user_id → req.external_user_id 直传
    - signed_jwt       → 验签 jwt_token，取 sub
    """
    policy = _resolve_session_policy(embed)
    mode = policy.identification_mode

    if mode == "anonymous_device":
        if not req.device_id:
            raise ValidationError(message="anonymous_device 模式需 device_id")
        return _hash_device_id(req.device_id)
    if mode == "external_user_id":
        if not req.external_user_id:
            raise ValidationError(message="external_user_id 模式需 external_user_id")
        return req.external_user_id
    if mode == "signed_jwt":
        if not req.jwt_token:
            raise ValidationError(message="signed_jwt 模式需 jwt_token")
        return _verify_jwt_and_extract_sub(policy, req.jwt_token)
    raise BusinessError(
        ResultCode.ValidationError, message=f"未知 identification_mode: {mode}"
    )


def _make_context(
    *,
    agent_key: str,
    app_key: str,
    user_input: str,
    request_id: str | None,
    stream: bool,
    session_id: str,
) -> InvokeContext:
    agent_def = AGENTS[agent_key]
    return InvokeContext(
        agent_def=agent_def,
        input=user_input,
        session_id=session_id,
        app_id=app_key,
        stream=stream,
        request_id=request_id,
    )


async def _ensure_session_matches(token: str, embed_id: int) -> None:
    bound = await embed_session.resolve_session(token)
    if bound != embed_id:
        raise BusinessError(
            ResultCode.JwtInvalid, message="session_token 与 embed_key 不匹配"
        )


# ── S11：embed-scope 的会话管理（按 end_user_id 隔离）────────


async def list_sessions_for_end_user(
    db_session: AsyncSession,
    *,
    embed: EmbedConfig,
    end_user_id: str | None,
    max_history_days: int = 90,
    limit: int = 50,
) -> list[ChatSession]:
    """列出某 embed 下某终端用户的历史会话（按活跃时间倒序）

    无 end_user_id（老 widget / 匿名 token 未绑用户）→ 返空，避免串号。
    """
    from datetime import datetime, timedelta, timezone

    if not end_user_id:
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=max_history_days)
    app_id = _embed_app_label(embed)
    agent = await _resolve_agent(db_session, embed)
    stmt = (
        select(ChatSession)
        .where(
            ChatSession.app_id == app_id,
            ChatSession.agent_key == agent.agent_key,
            ChatSession.end_user_id == end_user_id,
            ChatSession.deleted_at.is_(None),
            ChatSession.created_at >= cutoff,
        )
        .order_by(
            ChatSession.last_message_at.desc().nullslast(),
            ChatSession.created_at.desc(),
        )
        .limit(limit)
    )
    rows = (await db_session.execute(stmt)).scalars().all()
    return list(rows)


async def get_embed_session(
    db_session: AsyncSession,
    *,
    embed: EmbedConfig,
    session_id: str,
    end_user_id: str | None,
) -> ChatSession:
    """取某 embed 下 session_id 对应的会话（强校验 end_user_id 一致，防越权）"""
    app_id = _embed_app_label(embed)
    row = (
        await db_session.execute(
            select(ChatSession).where(
                ChatSession.session_id == session_id,
                ChatSession.app_id == app_id,
                ChatSession.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise BusinessError(
            ResultCode.SessionNotFound,
            message=f"session 不存在: {session_id}",
        )
    if end_user_id is not None and row.end_user_id and row.end_user_id != end_user_id:
        # 越权 → 表现为 NotFound（不泄漏存在性）
        raise BusinessError(
            ResultCode.SessionNotFound,
            message=f"session 不存在: {session_id}",
        )
    return row


async def soft_delete_embed_session(
    db_session: AsyncSession,
    *,
    embed: EmbedConfig,
    session_id: str,
    end_user_id: str | None,
) -> None:
    from datetime import datetime, timezone

    row = await get_embed_session(
        db_session, embed=embed, session_id=session_id, end_user_id=end_user_id
    )
    row.deleted_at = datetime.now(timezone.utc)
    # Phase B：级联清 SessionFile + 关联 ephemeral_kb（业务层）
    from chameleon.system.session_files import service as sf_svc

    await sf_svc.cascade_clean_for_session(db_session, session_id)
    await db_session.flush()


async def rename_embed_session(
    db_session: AsyncSession,
    *,
    embed: EmbedConfig,
    session_id: str,
    end_user_id: str | None,
    title: str,
) -> ChatSession:
    row = await get_embed_session(
        db_session, embed=embed, session_id=session_id, end_user_id=end_user_id
    )
    row.title = title[:255]
    await db_session.flush()
    return row


async def _ensure_session_row_for_embed(
    db_session: AsyncSession,
    *,
    session_id: str,
    embed: EmbedConfig,
    agent_key: str,
    end_user_id: str | None,
) -> ChatSession:
    """get-or-create —— 首次 embed 调用时往 sessions 表补一行，让 S11 列表端能查到。

    后续同一 sid 调用直接返回已有行（不重复创建）。
    """
    row = (
        await db_session.execute(
            select(ChatSession).where(ChatSession.session_id == session_id)
        )
    ).scalar_one_or_none()
    if row is not None:
        return row
    row = ChatSession(
        session_id=session_id,
        agent_key=agent_key,
        app_id=_embed_app_label(embed),
        api_key_id=embed.api_key_id,
        end_user_id=end_user_id,
    )
    db_session.add(row)
    await db_session.flush()
    return row


async def _write_log(
    session: AsyncSession,
    *,
    request_id: str,
    app_key: str,
    embed_key: str,
    agent_key: str,
    session_id: str | None,
    stream: bool,
    success: bool,
    code: int,
    error_message: str | None,
    duration_ms: int,
    usage: dict | None,
    user_input: str,
    answer: str,
    api_key_id: int | None = None,
    end_user_id: str | None = None,
) -> None:
    """call_logs 落表 —— embed 入口在 request_payload.source 标记，app_id 用 embed: 来源标签

    S10：归属冗余 api_key_id（embed 绑的 owner key）+ end_user_id（token 上绑的终端用户）
    """
    try:
        await record_call(
            session,
            request_id=request_id,
            app_id=app_key,
            agent_key=agent_key,
            session_id=session_id,
            channel="embed",
            stream=stream,
            success=success,
            code=code,
            error_message=error_message,
            duration_ms=duration_ms,
            prompt_tokens=(usage or {}).get("prompt_tokens"),
            completion_tokens=(usage or {}).get("completion_tokens"),
            total_tokens=(usage or {}).get("total_tokens"),
            request_payload={
                "input": user_input[:2000],
                "source": "embed",
                "embed_key": embed_key,
            },
            response_payload={"answer": answer[:2000]} if answer else None,
            observation_type="trace",
            api_key_id=api_key_id,
            end_user_id=end_user_id,
        )
        await session.commit()
    except Exception:  # noqa: BLE001
        logger.exception(
            "embed call_log write failed | embed_key={} | request_id={}",
            embed_key,
            request_id,
        )
        # log 落表失败不影响主流程
        try:
            await session.rollback()
        except Exception:  # noqa: BLE001
            pass


async def invoke_once(
    session: AsyncSession,
    *,
    embed: EmbedConfig,
    session_token: str,
    user_input: str,
    attachments: list[dict] | None = None,
    request_id: str | None,
) -> InvokeResult:
    """非流式调用 + 写 call_log"""
    await _ensure_session_matches(session_token, embed.id)
    await embed_session.check_rate_limit(session_token)
    agent = await _resolve_agent(session, embed)
    app_key = _embed_app_label(embed)
    rid = request_id or uuid.uuid4().hex
    sid = await embed_session.resolve_session_id(session_token)
    end_user_id = await embed_session.resolve_end_user_id(session_token)
    # S10：set TraceContext —— provider 内的 LLM 调用经 BaseLLM 回调自动落 generation 行
    set_trace_context(
        TraceContext(
            request_id=rid,
            channel="embed",
            app_id=app_key,
            api_key_id=embed.api_key_id,
            agent_key=agent.agent_key,
            session_id=sid,
            end_user_id=end_user_id,
        )
    )
    # Phase A 附件 → ContentBlock（仅图/音）；Phase B 文档/数据走 ephemeral RAG
    from chameleon.api.agent.service import blocks_from_attachments
    from chameleon.providers.base.types import Message as ProviderMessage
    from chameleon.system.session_files import service as session_file_svc

    blocks = blocks_from_attachments(user_input, attachments)
    ctx_input: object = user_input
    persist_blocks: list[dict] | None = None
    if blocks:
        ctx_input = [ProviderMessage(role="user", content=blocks)]
        persist_blocks = [b.model_dump() for b in blocks]

    # Phase B：落 SessionFile + 异步入临时 KB
    if attachments:
        await session_file_svc.record_attachments(
            session,
            session_id=sid,
            end_user_id=end_user_id,
            attachments=list(attachments),
        )

    ctx = _make_context(
        agent_key=agent.agent_key,
        app_key=app_key,
        user_input=user_input,
        request_id=rid,
        stream=False,
        session_id=sid,
    )
    if blocks:
        ctx.input = ctx_input  # 替换为多模态 Message 列表

    # Phase B：ephemeral RAG 注入 system message 到 ctx.history 头
    rag_hits = await session_file_svc.search_ephemeral(
        session, session_id=sid, query=user_input, top_k=5
    )
    if rag_hits:
        ctx.history = [
            ProviderMessage(
                role="system",
                content=session_file_svc.format_rag_system_prompt(rag_hits),
            ),
            *ctx.history,
        ]
        ctx.context_vars = {**ctx.context_vars, "ephemeral_citations": rag_hits}
    if attachments:
        ctx.attachments = list(attachments)

    provider = PROVIDERS[AGENTS[agent.agent_key].provider]

    # S11 桥：往 sessions 表补行 + 落 user message，让历史 API 能查到
    conv = await _ensure_session_row_for_embed(
        session,
        session_id=sid,
        embed=embed,
        agent_key=agent.agent_key,
        end_user_id=end_user_id,
    )
    await session_service.append(
        session,
        sid,
        AppendMessageDraft(
            role="user",
            content=user_input,
            content_blocks=persist_blocks,
            end_user_id=end_user_id,
        ),
    )

    start = time.monotonic()
    err: Exception | None = None
    result: InvokeResult | None = None
    try:
        result = await provider.invoke(ctx)
    except (BusinessError, ProviderError, ValidationError) as e:
        err = e
        raise
    except Exception as e:  # noqa: BLE001
        err = e
        raise
    finally:
        duration_ms = int((time.monotonic() - start) * 1000)
        # 成功 → 写 assistant message + touch（标题取首条 user 内容）
        if err is None and result is not None:
            await session_service.append(
                session,
                sid,
                AppendMessageDraft(
                    role="assistant",
                    content=result.answer,
                    usage=result.usage.model_dump() if result.usage else None,
                    end_user_id=end_user_id,
                ),
            )
            title = user_input if conv.title is None else None
            await session_service.touch(session, sid, title=title)
        await _write_log(
            session,
            request_id=rid,
            app_key=app_key,
            embed_key=embed.embed_key,
            agent_key=agent.agent_key,
            session_id=result.session_id if result else ctx.session_id,
            stream=False,
            success=err is None,
            code=ResultCode.Success if err is None else _classify_error_code(err),
            error_message=None if err is None else str(err)[:300],
            duration_ms=duration_ms,
            usage=result.usage.model_dump() if (result and result.usage) else None,
            user_input=user_input,
            answer=result.answer if result else "",
            api_key_id=embed.api_key_id,
            end_user_id=end_user_id,
        )
        try:
            await session.commit()
        except Exception:  # noqa: BLE001
            await session.rollback()
    assert result is not None
    return result


async def stream_invoke(
    session: AsyncSession,
    *,
    embed: EmbedConfig,
    session_token: str,
    user_input: str,
    attachments: list[dict] | None = None,
    request_id: str | None,
    show_citations: bool = True,
) -> AsyncIterator[dict]:
    """SSE 调用 + 末尾写 call_log。

    输出 chunk：
      - {"meta": {"agent": "...", "session_id": "...", "request_id": "..."}}
      - {"delta": "..."}                  # 文本片段
      - {"citation": {...}}                # 引用（show_citations=True 时）
      - {"end": True, "usage": {...}, "answer": "..."}
      - {"error": {"type": "...", "message": "..."}}
    """
    await _ensure_session_matches(session_token, embed.id)
    await embed_session.check_rate_limit(session_token)
    agent = await _resolve_agent(session, embed)
    app_key = _embed_app_label(embed)
    rid = request_id or uuid.uuid4().hex
    sid = await embed_session.resolve_session_id(session_token)
    end_user_id = await embed_session.resolve_end_user_id(session_token)
    # S10：set TraceContext —— provider 内的 LLM 调用经 BaseLLM 回调自动落 generation 行
    set_trace_context(
        TraceContext(
            request_id=rid,
            channel="embed",
            app_id=app_key,
            api_key_id=embed.api_key_id,
            agent_key=agent.agent_key,
            session_id=sid,
            end_user_id=end_user_id,
        )
    )
    # Phase A 附件 → ContentBlock；Phase B 文档/数据走 ephemeral RAG
    from chameleon.api.agent.service import blocks_from_attachments
    from chameleon.providers.base.types import Message as ProviderMessage
    from chameleon.system.session_files import service as session_file_svc

    blocks_s = blocks_from_attachments(user_input, attachments)
    persist_blocks_s: list[dict] | None = None
    if blocks_s:
        persist_blocks_s = [b.model_dump() for b in blocks_s]

    if attachments:
        await session_file_svc.record_attachments(
            session,
            session_id=sid,
            end_user_id=end_user_id,
            attachments=list(attachments),
        )

    ctx = _make_context(
        agent_key=agent.agent_key,
        app_key=app_key,
        user_input=user_input,
        request_id=rid,
        stream=True,
        session_id=sid,
    )
    if blocks_s:
        ctx.input = [ProviderMessage(role="user", content=blocks_s)]

    rag_hits_s = await session_file_svc.search_ephemeral(
        session, session_id=sid, query=user_input, top_k=5
    )
    if rag_hits_s:
        ctx.history = [
            ProviderMessage(
                role="system",
                content=session_file_svc.format_rag_system_prompt(rag_hits_s),
            ),
            *ctx.history,
        ]
        ctx.context_vars = {**ctx.context_vars, "ephemeral_citations": rag_hits_s}
    if attachments:
        ctx.attachments = list(attachments)

    provider = PROVIDERS[AGENTS[agent.agent_key].provider]

    # S11 桥：往 sessions 表补行 + 落 user message
    conv = await _ensure_session_row_for_embed(
        session,
        session_id=sid,
        embed=embed,
        agent_key=agent.agent_key,
        end_user_id=end_user_id,
    )
    await session_service.append(
        session,
        sid,
        AppendMessageDraft(
            role="user",
            content=user_input,
            content_blocks=persist_blocks_s,
            end_user_id=end_user_id,
        ),
    )
    await session.commit()  # 提交 user msg 防 stream 中断丢

    yield event_meta(
        agent=agent.agent_key,
        session_id=ctx.session_id,
        request_id=rid,
    )

    agg = _StreamAggregator(session_id=ctx.session_id, request_id=rid)
    start = time.monotonic()
    err: dict | None = None

    try:
        async for ev in provider.stream(ctx):
            agg.feed(ev)
            if ev.type == StreamEventType.delta:
                text = ev.data.get("text")
                if text:
                    yield event_delta(text)
            elif ev.type == StreamEventType.citation and show_citations:
                yield event_citation(ev.data)
            elif ev.type == StreamEventType.error:
                err = {
                    "type": ev.data.get("type", "ProviderError"),
                    "message": ev.data.get("message", "provider stream error"),
                }
                yield event_error(err["type"], err["message"])
                return
    except Exception as e:  # noqa: BLE001
        logger.exception("embed stream failed | embed={}", embed.embed_key)
        err = {"type": type(e).__name__, "message": str(e)[:300]}
        yield event_error(e)
    finally:
        duration_ms = int((time.monotonic() - start) * 1000)
        agg_result = agg.result()
        success = err is None
        if success:
            # Provider Usage 是 prompt_tokens/completion_tokens（OpenAI 命名）；
            # SSE 层统一用 input_tokens/output_tokens（LangFuse 命名）—— 边界翻译
            sse_usage: UsagePayload | None = None
            if agg_result.usage:
                pu = agg_result.usage
                sse_usage = UsagePayload(
                    input_tokens=pu.prompt_tokens or 0,
                    output_tokens=pu.completion_tokens or 0,
                    total_tokens=pu.total_tokens or 0,
                )
            yield event_end(usage=sse_usage, answer=agg_result.answer)
            # 落 assistant message + touch（与非流路径对齐）
            try:
                await session_service.append(
                    session,
                    sid,
                    AppendMessageDraft(
                        role="assistant",
                        content=agg_result.answer,
                        usage=agg_result.usage.model_dump()
                        if agg_result.usage
                        else None,
                        end_user_id=end_user_id,
                    ),
                )
                title = user_input if conv.title is None else None
                await session_service.touch(session, sid, title=title)
                await session.commit()
            except Exception:  # noqa: BLE001
                logger.exception(
                    "embed stream assistant persist failed | sid={}", sid
                )
                await session.rollback()
        await _write_log(
            session,
            request_id=rid,
            app_key=app_key,
            embed_key=embed.embed_key,
            agent_key=agent.agent_key,
            session_id=agg_result.session_id,
            stream=True,
            success=success,
            code=ResultCode.Success
            if success
            else ResultCode.ProviderInternalError,
            error_message=None if success else (err or {}).get("message"),
            duration_ms=duration_ms,
            usage=agg_result.usage.model_dump() if agg_result.usage else None,
            user_input=user_input,
            answer=agg_result.answer,
            api_key_id=embed.api_key_id,
            end_user_id=end_user_id,
        )


def _classify_error_code(exc: Exception) -> int:
    if isinstance(exc, BusinessError):
        return int(exc.code) if hasattr(exc, "code") else ResultCode.Fail
    if isinstance(exc, ValidationError):
        return ResultCode.ValidationError
    if isinstance(exc, ProviderError):
        return ResultCode.ProviderInternalError
    return ResultCode.InternalError
