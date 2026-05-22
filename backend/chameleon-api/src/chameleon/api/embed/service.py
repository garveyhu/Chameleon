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

from chameleon.api.embed import session as embed_session
from chameleon.core.api.exceptions import (
    BusinessError,
    PermissionDeniedError,
    ResultCode,
    ValidationError,
)
from chameleon.core.models import Agent, App, EmbedConfig
from chameleon.core.utils.snowflake import next_session_id
from chameleon.providers.base import AGENTS, PROVIDERS
from chameleon.providers.base.errors import ProviderError
from chameleon.providers.base.types import (
    InvokeContext,
    InvokeResult,
    StreamEvent,
    StreamEventType,
    _StreamAggregator,
)
from chameleon.system.api_key.service import record_call


def check_origin(allowed: list | None, origin: str | None) -> None:
    """同源 / 服务端调用允许；其余 origin 必须在白名单中。"""
    if origin is None:
        return
    if not allowed:
        raise PermissionDeniedError(message="该 embed 未配置 allowed_origins")
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


async def _resolve_app_key(session: AsyncSession, embed: EmbedConfig) -> str:
    """embed.app_id 是 apps.id（FK），call_logs.app_id 要用 apps.app_key 字符串"""
    app = (
        await session.execute(select(App).where(App.id == embed.app_id))
    ).scalar_one_or_none()
    if app is None:
        raise BusinessError(
            ResultCode.AgentNotFound, message=f"embed 关联 app 不存在: {embed.app_id}"
        )
    return app.app_key


def _make_context(
    *, agent_key: str, app_key: str, user_input: str, request_id: str | None, stream: bool
) -> InvokeContext:
    agent_def = AGENTS[agent_key]
    return InvokeContext(
        agent_def=agent_def,
        input=user_input,
        session_id=next_session_id(),
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
) -> None:
    """call_logs 落表 —— embed 入口在 request_payload.source 标记，app_id 用真实 apps.app_key"""
    try:
        await record_call(
            session,
            request_id=request_id,
            app_id=app_key,
            agent_key=agent_key,
            session_id=session_id,
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
    request_id: str | None,
) -> InvokeResult:
    """非流式调用 + 写 call_log"""
    await _ensure_session_matches(session_token, embed.id)
    await embed_session.check_rate_limit(session_token)
    agent = await _resolve_agent(session, embed)
    app_key = await _resolve_app_key(session, embed)
    rid = request_id or uuid.uuid4().hex
    ctx = _make_context(
        agent_key=agent.agent_key,
        app_key=app_key,
        user_input=user_input,
        request_id=rid,
        stream=False,
    )
    provider = PROVIDERS[AGENTS[agent.agent_key].provider]

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
        )
    assert result is not None
    return result


async def stream_invoke(
    session: AsyncSession,
    *,
    embed: EmbedConfig,
    session_token: str,
    user_input: str,
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
    app_key = await _resolve_app_key(session, embed)
    rid = request_id or uuid.uuid4().hex
    ctx = _make_context(
        agent_key=agent.agent_key,
        app_key=app_key,
        user_input=user_input,
        request_id=rid,
        stream=True,
    )
    provider = PROVIDERS[AGENTS[agent.agent_key].provider]

    yield {
        "meta": {
            "agent": agent.agent_key,
            "session_id": ctx.session_id,
            "request_id": rid,
        }
    }

    agg = _StreamAggregator(session_id=ctx.session_id, request_id=rid)
    start = time.monotonic()
    err: dict | None = None

    try:
        async for ev in provider.stream(ctx):
            agg.feed(ev)
            if ev.type == StreamEventType.delta:
                text = ev.data.get("text")
                if text:
                    yield {"delta": text}
            elif ev.type == StreamEventType.citation and show_citations:
                yield {"citation": ev.data}
            elif ev.type == StreamEventType.error:
                err = {
                    "type": ev.data.get("type", "ProviderError"),
                    "message": ev.data.get("message", "provider stream error"),
                }
                yield {"error": err}
                return
    except Exception as e:  # noqa: BLE001
        logger.exception("embed stream failed | embed={}", embed.embed_key)
        err = {"type": type(e).__name__, "message": str(e)[:300]}
        yield {"error": err}
    finally:
        duration_ms = int((time.monotonic() - start) * 1000)
        agg_result = agg.result()
        success = err is None
        if success:
            yield {
                "end": True,
                "usage": agg_result.usage.model_dump() if agg_result.usage else None,
                "answer": agg_result.answer,
            }
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
        )


def _classify_error_code(exc: Exception) -> int:
    if isinstance(exc, BusinessError):
        return int(exc.code) if hasattr(exc, "code") else ResultCode.Fail
    if isinstance(exc, ValidationError):
        return ResultCode.ValidationError
    if isinstance(exc, ProviderError):
        return ResultCode.ProviderInternalError
    return ResultCode.InternalError
