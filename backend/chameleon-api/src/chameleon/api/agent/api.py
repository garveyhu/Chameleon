"""agent 模块 HTTP 路由 —— Dify 风「key 即应用身份」唯一形式

主入口（仅此一个）：
  POST /v1/invoke   —— body.input；scope_type='app' 的 key 自动绑定 agent；
                      scope_type='global' 的 key 需带 body.agent_key 指定
  GET  /v1/info     —— 返回当前 key 绑定的应用信息

应用列表 / 详情 / 管理走 /v1/admin/agents/*（JWT 鉴权）；不暴露公开 /v1/agents/*。
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.api.agent import service
from chameleon.api.agent.schemas import (
    AgentItem,
    AttachmentInput,
    InvokeRequest,
    InvokeResponse,
    MessageInput,
)
from chameleon.api.agent.stream import sse_iter
from chameleon.core.api.exceptions import BusinessError, ResultCode
from chameleon.core.api.response import Result
from chameleon.data.infra.auth import CurrentApp, current_app
from chameleon.data.infra.db import get_session


def _resolve_agent_key_from_key(app: CurrentApp, body_agent_key: str | None) -> str:
    """从 key scope + body 解析目标 agent_key（Dify 套路：key 已隐含应用身份）

    - scope_type='app'：必须用 scope_ref（key 绑定的应用）；body.agent_key 若传需匹配
    - scope_type='global'：body.agent_key 必传
    - scope_type='kb' 等：禁止调 invoke
    """
    if app.scope_type == "app":
        target = app.scope_ref or ""
        if not target:
            raise BusinessError(
                ResultCode.ValidationError, message="app 作用域 key 缺 scope_ref"
            )
        if body_agent_key and body_agent_key != target:
            raise BusinessError(
                ResultCode.ValidationError,
                message=f"该 key 仅绑定 {target}，不可调 {body_agent_key}",
            )
        return target
    if app.scope_type == "global":
        if not body_agent_key:
            raise BusinessError(
                ResultCode.ValidationError,
                message="全局 key 需在 body 指定 agent_key",
            )
        return body_agent_key
    raise BusinessError(
        ResultCode.ValidationError,
        message=f"该 key 不支持 invoke（scope_type={app.scope_type}）",
    )


# ── Dify 风扁平入口 ────────────────────────────────────────


class FlatInvokeRequest(BaseModel):
    """扁平 POST /v1/invoke 入参 —— agent_key 由 key 隐含（app-key）或显式传（global-key）"""

    input: str | list[MessageInput] = Field(
        ..., description="str → 取 session 历史；list → 客户端自管历史"
    )
    attachments: list[AttachmentInput] | None = Field(
        None,
        description="本次调用附带的文件（图片走多模态；文档/数据 Phase B 起走临时 RAG）",
    )
    session_id: str | None = Field(
        None, description="缺省 → 新建会话；传入续接（同 agent + 同 end_user 才行）"
    )
    user: str | None = Field(
        None,
        description="终端用户外部标识（接入方维护，对应 Dify/OpenAI 的 user）",
    )
    stream: bool = Field(False, description="true → SSE；false → 单次 JSON")
    agent_key: str | None = Field(
        None,
        description="仅 global 作用域 key 需要；app-scoped key 不传或填 scope_ref 同值",
    )
    context: dict = Field(default_factory=dict)
    options: dict = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class AppInfoResponse(BaseModel):
    """GET /v1/info 返当前 key 代表的应用信息"""

    scope_type: str
    agent: AgentItem | None = None
    name: str  # key 自身的 name（来源标签）


flat_router = APIRouter(prefix="/v1", tags=["api"])


@flat_router.get("/info", response_model=Result[AppInfoResponse])
async def get_app_info(
    app: CurrentApp = Depends(current_app),
) -> Result[AppInfoResponse]:
    """返当前 key 绑定的应用信息 —— Dify GET /info 等价"""
    agent: AgentItem | None = None
    if app.scope_type == "app" and app.scope_ref:
        try:
            agent = service.get_agent(app.scope_ref)
        except Exception:  # noqa: BLE001
            agent = None
    return Result.ok(
        AppInfoResponse(scope_type=app.scope_type, agent=agent, name=app.name)
    )


@flat_router.post("/invoke", response_model=Result[InvokeResponse])
async def flat_invoke(
    req: FlatInvokeRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    app: CurrentApp = Depends(current_app),
):
    """扁平 invoke —— key 即应用身份（Dify 套路）"""
    request_id = getattr(request.state, "request_id", "req_unknown")
    agent_key = _resolve_agent_key_from_key(app, req.agent_key)
    inner_req = InvokeRequest(
        input=req.input,
        attachments=req.attachments,
        session_id=req.session_id,
        user=req.user,
        stream=req.stream,
        context=req.context,
        options=req.options,
    )
    if req.stream:
        return StreamingResponse(
            sse_iter(
                service.stream_invoke(
                    agent_key, inner_req, current_app=app, request_id=request_id
                )
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "X-Request-Id": request_id,
            },
        )
    resp = await service.invoke(
        session, agent_key, inner_req, current_app=app, request_id=request_id
    )
    return Result.ok(resp)


