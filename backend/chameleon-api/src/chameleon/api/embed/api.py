"""嵌入式业务 HTTP 路由 (/v1/embed/{embed_key}/*)

接口：
- GET  /config       拉 ui_config + behavior（带 origin 白名单校验）
- POST /session      颁 session_token
- POST /invoke       用 session_token 调对应 agent（非流；流式后续 P9 加 SSE）
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.api.embed import session as embed_session
from chameleon.core.api.exceptions import (
    BusinessError,
    PermissionDeniedError,
    ResultCode,
    ValidationError,
)
from chameleon.core.api.response import Result
from chameleon.core.infra.db import get_session
from chameleon.core.models import Agent, EmbedConfig
from chameleon.core.utils.snowflake import next_session_id
from chameleon.providers.base import AGENTS, PROVIDERS
from chameleon.providers.base.types import InvokeContext


# ── DTO ────────────────────────────────────────────────────


class EmbedPublicConfig(BaseModel):
    """业务方网页能拿到的公开配置（不含 agent_id / app_id 等内部 ID）"""

    embed_key: str
    name: str
    description: str | None = None
    ui_config: dict | None = None
    behavior: dict | None = None
    welcome_message: str | None = None  # 兼容 behavior.welcome_message 顶层


class CreateSessionResponse(BaseModel):
    session_token: str
    expires_in: int  # 秒


class InvokeRequest(BaseModel):
    session_token: str
    input: str = Field(min_length=1, max_length=8000)


class InvokeResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    answer: str
    session_id: str
    request_id: str | None = None


# ── Origin 校验 ────────────────────────────────────────────


def _check_origin(allowed: list | None, origin: str | None) -> None:
    """origin 不在 allowed 中 → 403

    allowed 为 None / 空 → 拒绝所有跨域请求（要求 widget 配置了 origin）。
    特殊：origin 为 None（同源 / 服务端调用） → 通过。
    """
    if origin is None:
        return  # 同源或服务端直调
    if not allowed:
        raise PermissionDeniedError(message="该 embed 未配置 allowed_origins")
    if origin not in allowed:
        raise PermissionDeniedError(message=f"origin 不在白名单: {origin}")


# ── helpers ────────────────────────────────────────────────


async def _resolve_config(
    session: AsyncSession, embed_key: str
) -> EmbedConfig:
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


# ── 路由 ───────────────────────────────────────────────────


router = APIRouter(prefix="/v1/embed", tags=["embed"])


@router.get("/{embed_key}/config", response_model=Result[EmbedPublicConfig])
async def get_public_config(
    embed_key: str,
    origin: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> Result[EmbedPublicConfig]:
    """业务方 widget 首次加载时拉配置"""
    e = await _resolve_config(session, embed_key)
    _check_origin(e.allowed_origins, origin)
    welcome = (e.behavior or {}).get("welcome_message")
    return Result.ok(
        EmbedPublicConfig(
            embed_key=e.embed_key,
            name=e.name,
            description=e.description,
            ui_config=e.ui_config,
            behavior=e.behavior,
            welcome_message=welcome,
        )
    )


@router.post("/{embed_key}/session", response_model=Result[CreateSessionResponse])
async def create_session(
    embed_key: str,
    origin: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> Result[CreateSessionResponse]:
    """用户点开 widget 时颁 session_token"""
    e = await _resolve_config(session, embed_key)
    _check_origin(e.allowed_origins, origin)
    token, ttl = await embed_session.create_session(e.id)
    return Result.ok(CreateSessionResponse(session_token=token, expires_in=ttl))


@router.post("/{embed_key}/invoke", response_model=Result[InvokeResponse])
async def invoke(
    embed_key: str,
    req: InvokeRequest,
    request: Request,
    origin: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> Result[InvokeResponse]:
    """用户发消息 → 调对应 agent（非流式）"""
    e = await _resolve_config(session, embed_key)
    _check_origin(e.allowed_origins, origin)

    # 校验 session_token 关联的 embed_config_id 与 URL 一致
    bound_id = await embed_session.resolve_session(req.session_token)
    if bound_id != e.id:
        raise BusinessError(
            ResultCode.JwtInvalid, message="session_token 与 embed_key 不匹配"
        )

    # 限流
    await embed_session.check_rate_limit(req.session_token)

    # 找 agent → 用 PROVIDERS[source].invoke
    agent = (
        await session.execute(
            select(Agent).where(
                Agent.id == e.agent_id, Agent.deleted_at.is_(None)
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

    agent_def = AGENTS[agent.agent_key]
    provider = PROVIDERS.get(agent_def.provider)
    if provider is None:
        raise BusinessError(
            ResultCode.RegistryError,
            message=f"provider {agent_def.provider} 未注册",
        )

    ctx = InvokeContext(
        agent_def=agent_def,
        input=req.input,
        session_id=next_session_id(),
        app_id=f"__embed_{e.embed_key}__",
        stream=False,
        request_id=request.headers.get("X-Request-Id"),
    )
    result = await provider.invoke(ctx)
    return Result.ok(
        InvokeResponse(
            answer=result.answer,
            session_id=result.session_id,
            request_id=result.request_id,
        )
    )
