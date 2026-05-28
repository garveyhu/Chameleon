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
from chameleon.api.embed.schemas import (
    CreateNewSessionResponse,
    CreateSessionRequest,
    EmbedSessionItem,
    RenameSessionRequest,
)
from chameleon.api.sessions.schemas import MessageItem
from chameleon.core.models import Message
from chameleon.core.utils.snowflake import next_session_id
from sqlalchemy import select
from chameleon.core.api.response import Result
from chameleon.core.api.sse import sse_response
from chameleon.core.infra.db import get_session
from chameleon.system.scores import service as score_service
from chameleon.system.scores.schemas import FeedbackRequest, ScoreItem


# ── DTO ────────────────────────────────────────────────────


class EmbedPublicConfig(BaseModel):
    """业务方网页能拿到的公开配置（不含 agent_id / app_id 等内部 ID）

    session_policy 里只暴露给 widget 需要的开关（identification_mode /
    show_history_sidebar / auto_resume_last / allow_user_manage / max_history_days），
    密钥（jwt_signing_secret_encrypted）由后端服务端使用，绝不下发。
    """

    embed_key: str
    name: str
    description: str | None = None
    ui_config: dict | None = None
    behavior: dict | None = None
    session_policy: dict | None = None


class CreateSessionResponse(BaseModel):
    session_token: str
    expires_in: int  # 秒


class _EmbedAttachment(BaseModel):
    object_url: str
    filename: str | None = Field(None, max_length=255)
    mime: str
    size: int | None = Field(None, ge=0)


class InvokeRequest(BaseModel):
    session_token: str
    input: str = Field(min_length=1, max_length=8000)
    attachments: list[_EmbedAttachment] | None = Field(
        None,
        description="本次调用附带的文件（图片走多模态；其他类型 Phase B 起走临时 RAG）",
    )


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
    # 仅暴露非机密字段；密钥（jwt_signing_secret_encrypted）剥掉
    policy_raw = dict(e.session_policy or {})
    policy_raw.pop("jwt_signing_secret_encrypted", None)
    return Result.ok(
        EmbedPublicConfig(
            embed_key=e.embed_key,
            name=e.name,
            description=e.description,
            ui_config=e.ui_config,
            behavior=e.behavior,
            session_policy=policy_raw or None,
        )
    )


@router.post("/{embed_key}/session", response_model=Result[CreateSessionResponse])
async def create_session(
    embed_key: str,
    req: CreateSessionRequest | None = None,
    origin: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> Result[CreateSessionResponse]:
    """用户打开 widget 时颁 session_token

    S10：body 可选传 device_id / external_user_id / jwt_token；按 embed 的
    session_policy.identification_mode 解析终端用户 id 并绑到 token。老 widget
    不传 body 时返回未绑用户的 token（向后兼容；后续按 anonymous fallback）。
    """
    e = await embed_service.resolve_embed(session, embed_key)
    embed_service.check_origin(e.allowed_origins, origin)
    end_user_id: str | None = None
    if req is not None:
        end_user_id = embed_service.resolve_end_user_from_request(e, req)
    token, _sid, ttl = await embed_session.create_session(
        e.id, end_user_id=end_user_id
    )
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
        attachments=[a.model_dump() for a in (req.attachments or [])],
        request_id=request.headers.get("X-Request-Id"),
    )
    return Result.ok(
        InvokeResponse(
            answer=result.answer,
            session_id=result.session_id,
            request_id=result.request_id,
        )
    )


# ── S11：会话管理（按 session_token 解析 end_user_id 隔离）─────────


class _TokenedRequest(BaseModel):
    """所有 S11 端点共用的入参基础 —— 至少传 session_token，按 origin + token 鉴权"""

    session_token: str


class _DeleteSessionRequest(_TokenedRequest):
    pass


class _RenameSessionWithToken(_TokenedRequest):
    title: str = Field(min_length=1, max_length=255)


async def _resolve_token_context(
    embed_key: str,
    session_token: str,
    origin: str | None,
    session: AsyncSession,
):
    """共用前置：解析 embed + 校验 origin + 校验 token 归属 + 取 end_user_id"""
    e = await embed_service.resolve_embed(session, embed_key)
    embed_service.check_origin(e.allowed_origins, origin)
    bound = await embed_session.resolve_session(session_token)
    if bound != e.id:
        from chameleon.core.api.exceptions import BusinessError, ResultCode
        raise BusinessError(
            ResultCode.JwtInvalid, message="session_token 与 embed_key 不匹配"
        )
    end_user_id = await embed_session.resolve_end_user_id(session_token)
    return e, end_user_id


@router.get(
    "/{embed_key}/sessions",
    response_model=Result[list[EmbedSessionItem]],
)
async def list_my_sessions(
    embed_key: str,
    session_token: str,  # query param（GET 没法带 body）
    origin: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> Result[list[EmbedSessionItem]]:
    """当前终端用户的历史会话（按活跃时间倒序）"""
    e, end_user_id = await _resolve_token_context(
        embed_key, session_token, origin, session
    )
    rows = await embed_service.list_sessions_for_end_user(
        session, embed=e, end_user_id=end_user_id
    )
    items = [
        EmbedSessionItem(
            session_id=r.session_id,
            title=r.title,
            last_message_at=r.last_message_at.isoformat() if r.last_message_at else None,
            created_at=r.created_at.isoformat(),
        )
        for r in rows
    ]
    return Result.ok(items)


@router.get(
    "/{embed_key}/sessions/{session_id}/messages",
    response_model=Result[list[MessageItem]],
)
async def list_my_session_messages(
    embed_key: str,
    session_id: str,
    session_token: str,
    origin: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> Result[list[MessageItem]]:
    """切到某历史会话，加载消息列表（按 seq 正序）+ rebind token 到此 sid

    隐式 side-effect：拉某个老会话的消息 = 用户要切到这个会话上继续聊；
    所以拉消息时顺手把 token 上绑的 sid 切过去，下一条 invoke 就落入这个老
    会话。仅看不发等价于不发消息，sid 切过去也无害。
    """
    e, end_user_id = await _resolve_token_context(
        embed_key, session_token, origin, session
    )
    # 越权校验（不存在 / 不属于该 end_user → 都 throw SessionNotFound）
    await embed_service.get_embed_session(
        session, embed=e, session_id=session_id, end_user_id=end_user_id
    )
    rows = (
        (
            await session.execute(
                select(Message)
                .where(Message.session_id == session_id)
                .order_by(Message.seq.asc())
                .limit(500)  # embed 不分页，硬上限防爆
            )
        )
        .scalars()
        .all()
    )
    items = [MessageItem.model_validate(r) for r in rows]
    # 顺手把 token 上绑的 sid 切过去（前端续接的核心一步）
    await embed_session.rebind_session_id(session_token, session_id)
    return Result.ok(items)


@router.post(
    "/{embed_key}/sessions/new",
    response_model=Result[CreateNewSessionResponse],
)
async def open_new_session(
    embed_key: str,
    req: _TokenedRequest,
    origin: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> Result[CreateNewSessionResponse]:
    """显式开新对话 —— 同 token 直接 rebind 一个新 session_id（不需要刷新页面）"""
    e, end_user_id = await _resolve_token_context(
        embed_key, req.session_token, origin, session
    )
    del e  # 仅用于鉴权侧效应
    new_sid = next_session_id()
    await embed_session.rebind_session_id(req.session_token, new_sid)
    return Result.ok(
        CreateNewSessionResponse(
            session_token=req.session_token,
            session_id=new_sid,
            expires_in=embed_session.SESSION_TTL_SECONDS,
        )
    )


@router.post(
    "/{embed_key}/sessions/{session_id}/delete",
    response_model=Result[dict],
)
async def delete_my_session(
    embed_key: str,
    session_id: str,
    req: _DeleteSessionRequest,
    origin: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> Result[dict]:
    """end-user 软删自己的会话；受 session_policy.allow_user_manage 限制"""
    e, end_user_id = await _resolve_token_context(
        embed_key, req.session_token, origin, session
    )
    policy = embed_service._resolve_session_policy(e)
    if not policy.allow_user_manage:
        from chameleon.core.api.exceptions import PermissionDeniedError
        raise PermissionDeniedError(message="该嵌入应用未开放会话自管理")
    await embed_service.soft_delete_embed_session(
        session, embed=e, session_id=session_id, end_user_id=end_user_id
    )
    await session.commit()
    return Result.ok({"deleted": True})


@router.post(
    "/{embed_key}/sessions/{session_id}/name",
    response_model=Result[EmbedSessionItem],
)
async def rename_my_session(
    embed_key: str,
    session_id: str,
    req: _RenameSessionWithToken,
    origin: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> Result[EmbedSessionItem]:
    """end-user 重命名会话；受 session_policy.allow_user_manage 限制"""
    e, end_user_id = await _resolve_token_context(
        embed_key, req.session_token, origin, session
    )
    policy = embed_service._resolve_session_policy(e)
    if not policy.allow_user_manage:
        from chameleon.core.api.exceptions import PermissionDeniedError
        raise PermissionDeniedError(message="该嵌入应用未开放会话自管理")
    row = await embed_service.rename_embed_session(
        session,
        embed=e,
        session_id=session_id,
        end_user_id=end_user_id,
        title=req.title,
    )
    await session.commit()
    return Result.ok(
        EmbedSessionItem(
            session_id=row.session_id,
            title=row.title,
            last_message_at=row.last_message_at.isoformat()
            if row.last_message_at
            else None,
            created_at=row.created_at.isoformat(),
        )
    )


# ── 原有 feedback ─────────────────────────────────────────


class _FollowupsRequest(_TokenedRequest):
    question: str = Field(min_length=1, max_length=2000)
    answer: str = Field(min_length=1, max_length=8000)


@router.post(
    "/{embed_key}/suggest-followups",
    response_model=Result[list[str]],
)
async def suggest_followups(
    embed_key: str,
    req: _FollowupsRequest,
    origin: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> Result[list[str]]:
    """基于刚才的问答生成 3 个建议追问 —— widget 在 SSE end 后调用，按
    behavior.show_followups 渲染气泡。鉴权同 invoke（origin + session_token）。"""
    await _resolve_token_context(embed_key, req.session_token, origin, session)
    from chameleon.system.graphs import generator as graph_generator

    return Result.ok(await graph_generator.suggest_followups(req.question, req.answer))


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
            attachments=[a.model_dump() for a in (req.attachments or [])],
            request_id=request.headers.get("X-Request-Id"),
            show_citations=show_citations,
        ),
        log_label=f"embed:{embed_key}",
    )
