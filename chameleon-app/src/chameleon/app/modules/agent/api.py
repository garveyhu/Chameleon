"""agent 模块 HTTP 路由

挂点：
  POST /v1/agents/{key}/invoke      —— 非流式（P4 接 SSE 流式）
  GET  /v1/agents                   —— 列表
  GET  /v1/agents/{key}             —— 详情
"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.app.modules.agent import service
from chameleon.app.modules.agent.schemas import (
    AgentItem,
    InvokeRequest,
    InvokeResponse,
)
from chameleon.core.auth import CurrentApp, current_app
from chameleon.core.db import get_session
from chameleon.core.exceptions import BusinessError, ResultCode
from chameleon.core.response import Result

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


@router.post("/{key}/invoke", response_model=Result[InvokeResponse])
async def invoke_agent(
    key: str,
    req: InvokeRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    app: CurrentApp = Depends(current_app),
) -> Result[InvokeResponse]:
    if req.stream:
        # P4 实现 SSE 路径；P3 阶段拒绝
        raise BusinessError(
            ResultCode.InvalidStreamMode,
            message="stream=true 暂未实现（Phase 4 接入）",
        )

    request_id = getattr(request.state, "request_id", "req_unknown")
    resp = await service.invoke(
        session,
        key,
        req,
        current_app=app,
        request_id=request_id,
    )
    return Result.ok(resp)
