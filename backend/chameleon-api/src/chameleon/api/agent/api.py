"""agent 模块 HTTP 路由

挂点：
  POST /v1/agents/{key}/invoke      —— stream by body field
  GET  /v1/agents                   —— 列表
  GET  /v1/agents/{key}             —— 详情
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.api.agent import service
from chameleon.api.agent.schemas import (
    AgentItem,
    InvokeRequest,
    InvokeResponse,
)
from chameleon.api.agent.stream import sse_iter
from chameleon.core.infra.auth import CurrentApp, current_app
from chameleon.core.infra.db import get_session
from chameleon.core.api.response import Result

router = APIRouter(prefix="/v1/agents", tags=["agents"])


@router.get("", response_model=Result[list[AgentItem]])
async def list_agents(
    _: CurrentApp = Depends(current_app),
) -> Result[list[AgentItem]]:
    return Result.ok(service.list_agents())


@router.get("/{key}", response_model=Result[AgentItem])
async def get_agent(
    key: str,
    _: CurrentApp = Depends(current_app),
) -> Result[AgentItem]:
    return Result.ok(service.get_agent(key))


@router.post(
    "/{key}/invoke",
    # response_model 仅描述非流模式；流式返 text/event-stream
    response_model=Result[InvokeResponse],
)
async def invoke_agent(
    key: str,
    req: InvokeRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    app: CurrentApp = Depends(current_app),
):
    request_id = getattr(request.state, "request_id", "req_unknown")

    if req.stream:
        # 流式：自管 session（service.stream_invoke 内部），返 SSE StreamingResponse
        return StreamingResponse(
            sse_iter(
                service.stream_invoke(
                    key,
                    req,
                    current_app=app,
                    request_id=request_id,
                )
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",  # 防 Nginx 缓冲
                "X-Request-Id": request_id,
            },
        )

    # 非流式
    resp = await service.invoke(
        session,
        key,
        req,
        current_app=app,
        request_id=request_id,
    )
    return Result.ok(resp)
