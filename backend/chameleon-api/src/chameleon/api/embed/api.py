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


# ── Phase E：嵌入端走 origin+token 鉴权的文件上传（不需要 API Key） ─────


class _EmbedPresignBody(BaseModel):
    """widget 上传文件时调用，鉴权同 invoke（origin + session_token）"""

    session_token: str
    filename: str = Field(min_length=1, max_length=256)
    content_type: str = Field(min_length=1, max_length=128)
    size: int = Field(ge=1)


class _EmbedFinalizeBody(BaseModel):
    session_token: str
    expected_size: int | None = None


# ── 附件配置默认值（与 widget / admin 表单对齐） ─────────────────
_DEFAULT_MAX_FILE_SIZE_MB = 10
_DEFAULT_MAX_FILES_PER_MESSAGE = 5
_DEFAULT_ALLOWED_FILE_KINDS = ["image", "audio", "document", "data"]


def _file_limits(behavior: dict | None) -> tuple[int, int, list[str]]:
    """从 behavior 配置里取 (max_size_bytes, max_files_per_message, allowed_kinds)"""
    b = behavior or {}
    max_mb = int(b.get("max_file_size_mb") or _DEFAULT_MAX_FILE_SIZE_MB)
    if max_mb <= 0:
        max_mb = _DEFAULT_MAX_FILE_SIZE_MB
    max_per_msg = int(b.get("max_files_per_message") or _DEFAULT_MAX_FILES_PER_MESSAGE)
    if max_per_msg <= 0:
        max_per_msg = _DEFAULT_MAX_FILES_PER_MESSAGE
    kinds = b.get("allowed_file_kinds")
    if not isinstance(kinds, list) or not kinds:
        kinds = list(_DEFAULT_ALLOWED_FILE_KINDS)
    return max_mb * 1024 * 1024, max_per_msg, [str(k) for k in kinds]


def _enforce_file_limits(
    *, behavior: dict | None, size: int, mime: str
) -> None:
    """presign / finalize 前置校验：大小 + 类型 kind 是否被允许"""
    from chameleon.core.api.exceptions import BusinessError, ResultCode
    from chameleon.system.session_files.service import classify_kind

    max_bytes, _, allowed = _file_limits(behavior)
    if size > max_bytes:
        raise BusinessError(
            ResultCode.BadRequest,
            message=f"文件超过大小上限（{max_bytes // (1024 * 1024)}MB）",
        )
    kind = classify_kind(mime)
    if kind not in allowed:
        raise BusinessError(
            ResultCode.BadRequest,
            message=f"该类型文件未被允许上传（{kind}）",
        )


@router.post("/{embed_key}/files/presigned-upload")
async def embed_files_presigned(
    embed_key: str,
    body: _EmbedPresignBody,
    origin: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
):
    """widget 走的 presigned-upload：origin + session_token 鉴权 + 按 behavior 配置校验大小/类型"""
    e, _ = await _resolve_token_context(embed_key, body.session_token, origin, session)
    _enforce_file_limits(behavior=e.behavior, size=body.size, mime=body.content_type)

    from chameleon.api.files.api import build_presigned_upload
    from chameleon.api.files.schemas import PresignedUploadRequest

    inner = PresignedUploadRequest(
        filename=body.filename,
        content_type=body.content_type,
        size=body.size,
        namespace=f"embed-attach/{embed_key}",
    )
    return Result.ok(build_presigned_upload(inner))


@router.post("/{embed_key}/files/{object_id:path}/finalize")
async def embed_files_finalize(
    embed_key: str,
    object_id: str,
    body: _EmbedFinalizeBody,
    origin: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
):
    """widget 走的 finalize：鉴权同上；同时把附件落 SessionFile + 异步入临时 KB，
    让用户即使不立刻发消息，文件也已暂存在当前会话上 ——
    下一次发消息时 RAG 直接命中（不必再等 parsing）。
    """
    e, end_user_id = await _resolve_token_context(
        embed_key, body.session_token, origin, session
    )
    from chameleon.api.files.api import finalize_uploaded_object
    from chameleon.api.files.schemas import FinalizeRequest
    from chameleon.api.embed import session as embed_session_mod
    from chameleon.system.session_files import service as sf_svc

    inner = FinalizeRequest(expected_size=body.expected_size)
    fin = finalize_uploaded_object(object_id, inner)
    # 兜底（widget 可能绕过 presign 直接 PUT MinIO，所以 finalize 再校一遍）
    _enforce_file_limits(behavior=e.behavior, size=fin.size, mime=fin.content_type or "")

    # 立刻把附件挂到当前会话上（record_attachments：文档类异步解析）
    sid = await embed_session_mod.resolve_session_id(body.session_token)
    rows = await sf_svc.record_attachments(
        session,
        session_id=sid,
        end_user_id=end_user_id,
        attachments=[
            {
                "object_url": fin.object_url,
                "object_id": fin.object_id,
                "filename": object_id.rsplit("/", 1)[-1],
                "mime": fin.content_type or "application/octet-stream",
                "size": fin.size,
            }
        ],
    )
    await session.commit()
    # 把 SessionFile id + 当前 status 透出给 widget 做后续 status polling
    sf_id = rows[0].id if rows else None
    sf_status = rows[0].status if rows else "ready"
    payload = fin.model_dump() if hasattr(fin, "model_dump") else dict(fin)
    payload["session_file_id"] = sf_id
    payload["status"] = sf_status
    return Result.ok(payload)


class _EmbedFileStatusBody(BaseModel):
    session_token: str


class _EmbedFileStatus(BaseModel):
    id: int
    status: str
    error: str | None = None


@router.post(
    "/{embed_key}/files/{file_id}/status",
    response_model=Result[_EmbedFileStatus],
)
async def embed_file_status(
    embed_key: str,
    file_id: int,
    body: _EmbedFileStatusBody,
    origin: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> Result[_EmbedFileStatus]:
    """widget 轮询附件解析状态：uploaded → parsing → indexing → ready / failed"""
    e, end_user_id = await _resolve_token_context(
        embed_key, body.session_token, origin, session
    )
    from chameleon.core.api.exceptions import BusinessError, ResultCode
    from chameleon.system.session_files import service as sf_svc

    sf = await sf_svc.get_one(session, file_id)
    sid = await embed_session.resolve_session_id(body.session_token)
    if sf.session_id != sid or (
        end_user_id and sf.end_user_id and sf.end_user_id != end_user_id
    ):
        raise BusinessError(ResultCode.NotFound, message="文件不存在或不属于该会话")
    return Result.ok(_EmbedFileStatus(id=sf.id, status=sf.status, error=sf.error))


# ── Phase B：会话级附件管理（list / delete） ──────────────


class _EmbedFileItem(BaseModel):
    id: int
    filename: str
    mime: str
    size: int
    kind: str
    status: str
    object_url: str
    created_at: str


@router.get(
    "/{embed_key}/sessions/{session_id}/files",
    response_model=Result[list[_EmbedFileItem]],
)
async def list_session_files(
    embed_key: str,
    session_id: str,
    session_token: str,
    origin: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> Result[list[_EmbedFileItem]]:
    """end-user 拉自己在此会话上传的附件列表（受 end_user 隔离）"""
    e, end_user_id = await _resolve_token_context(
        embed_key, session_token, origin, session
    )
    # 越权校验：session 必须属于这个 end_user
    await embed_service.get_embed_session(
        session, embed=e, session_id=session_id, end_user_id=end_user_id
    )
    from chameleon.system.session_files import service as sf_svc

    rows = await sf_svc.list_for_session(
        session, session_id=session_id, end_user_id=end_user_id
    )
    items = [
        _EmbedFileItem(
            id=r.id,
            filename=r.filename,
            mime=r.mime,
            size=r.size,
            kind=r.kind,
            status=r.status,
            object_url=r.object_url,
            created_at=r.created_at.isoformat(),
        )
        for r in rows
    ]
    return Result.ok(items)


@router.post(
    "/{embed_key}/sessions/{session_id}/files/{file_id}/delete",
    response_model=Result[dict],
)
async def delete_session_file(
    embed_key: str,
    session_id: str,
    file_id: int,
    req: _TokenedRequest,
    origin: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> Result[dict]:
    """end-user 删自己上传的附件 + 级联清相关资源（document/chunks/MinIO）"""
    e, end_user_id = await _resolve_token_context(
        embed_key, req.session_token, origin, session
    )
    await embed_service.get_embed_session(
        session, embed=e, session_id=session_id, end_user_id=end_user_id
    )
    from chameleon.system.session_files import service as sf_svc

    sf = await sf_svc.get_one(session, file_id)
    if sf.session_id != session_id or (
        end_user_id and sf.end_user_id and sf.end_user_id != end_user_id
    ):
        from chameleon.core.api.exceptions import BusinessError, ResultCode

        raise BusinessError(
            ResultCode.NotFound, message="文件不存在或不属于该会话"
        )
    await sf_svc.soft_delete(session, file_id)
    await session.commit()
    return Result.ok({"deleted": True})


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
