"""嵌入式业务 HTTP 路由 (/v1/embed/{embed_key}/*)

接口：
- GET  /config         拉 ui_config + behavior（带 origin 白名单校验）
- POST /session        颁 session_token
- POST /invoke         非流式调用（写 call_log）
- POST /invoke/stream  SSE 流式调用（写 call_log）

业务编排在 service.py，本文件零业务。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.api.embed import service as embed_service
from chameleon.api.embed import session as embed_session
from chameleon.core.api.response import Result
from chameleon.core.api.sse import sse_response
from chameleon.core.infra.db import get_session
from chameleon.system.scores import service as score_service
from chameleon.system.scores.schemas import FeedbackRequest, ScoreItem


# ── DTO ────────────────────────────────────────────────────


class EmbedPublicConfig(BaseModel):
    """业务方网页能拿到的公开配置（不含 agent_id / app_id 等内部 ID）"""

    embed_key: str
    name: str
    description: str | None = None
    ui_config: dict | None = None
    behavior: dict | None = None


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


# ── 路由 ───────────────────────────────────────────────────


router = APIRouter(prefix="/v1/embed", tags=["embed"])


@router.get("/{embed_key}/config", response_model=Result[EmbedPublicConfig])
async def get_public_config(
    embed_key: str,
    origin: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> Result[EmbedPublicConfig]:
    """业务方 widget 首次加载时拉配置"""
    e = await embed_service.resolve_embed(session, embed_key)
    embed_service.check_origin(e.allowed_origins, origin)
    return Result.ok(
        EmbedPublicConfig(
            embed_key=e.embed_key,
            name=e.name,
            description=e.description,
            ui_config=e.ui_config,
            behavior=e.behavior,
        )
    )


@router.post("/{embed_key}/session", response_model=Result[CreateSessionResponse])
async def create_session(
    embed_key: str,
    origin: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> Result[CreateSessionResponse]:
    """用户打开 widget 时颁 session_token"""
    e = await embed_service.resolve_embed(session, embed_key)
    embed_service.check_origin(e.allowed_origins, origin)
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
    """非流式调用"""
    e = await embed_service.resolve_embed(session, embed_key)
    embed_service.check_origin(e.allowed_origins, origin)
    result = await embed_service.invoke_once(
        session,
        embed=e,
        session_token=req.session_token,
        user_input=req.input,
        request_id=request.headers.get("X-Request-Id"),
    )
    return Result.ok(
        InvokeResponse(
            answer=result.answer,
            session_id=result.session_id,
            request_id=result.request_id,
        )
    )


@router.post("/{embed_key}/feedback", response_model=Result[ScoreItem])
async def submit_feedback(
    embed_key: str,
    req: FeedbackRequest,
    origin: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> Result[ScoreItem]:
    """业务方 widget 反馈入口（👍 / 👎 / 评分 / 评语）

    校验 embed_key 合法 + origin 白名单后写入 scores 表，
    source 固定 'feedback' 与人工标注 / eval 区分。
    """
    e = await embed_service.resolve_embed(session, embed_key)
    embed_service.check_origin(e.allowed_origins, origin)
    item = await score_service.record_feedback(session, req, source="feedback")
    return Result.ok(item)


@router.post("/{embed_key}/invoke/stream")
async def invoke_stream(
    embed_key: str,
    req: InvokeRequest,
    request: Request,
    origin: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
):
    """SSE 流式调用：chunk 协议详见 service.stream_invoke 注释。"""
    e = await embed_service.resolve_embed(session, embed_key)
    embed_service.check_origin(e.allowed_origins, origin)
    show_citations = bool(((e.behavior or {}).get("show_citations", True)))
    return sse_response(
        embed_service.stream_invoke(
            session,
            embed=e,
            session_token=req.session_token,
            user_input=req.input,
            request_id=request.headers.get("X-Request-Id"),
            show_citations=show_citations,
        ),
        log_label=f"embed:{embed_key}",
    )
