"""graphs HTTP 路由（/v1/admin/graphs）"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.api.response import Result
from chameleon.core.infra.db import get_session
from chameleon.system.auth.dependencies import require_permission
from chameleon.system.graphs import service as graph_service
from chameleon.system.graphs.schemas import (
    CreateGraphRequest,
    GraphDetail,
    GraphItem,
    TestRunRequest,
    TestRunResult,
    UpdateGraphRequest,
)

router = APIRouter(prefix="/v1/admin/graphs", tags=["admin:graphs"])


@router.get("", response_model=Result[list[GraphItem]])
async def list_graphs(
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("graphs:read")),
) -> Result[list[GraphItem]]:
    items = await graph_service.list_graphs(session)
    return Result.ok(items)


@router.get("/{graph_id}", response_model=Result[GraphDetail])
async def get_graph(
    graph_id: int,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("graphs:read")),
) -> Result[GraphDetail]:
    item = await graph_service.get_graph(session, graph_id)
    return Result.ok(item)


@router.post("", response_model=Result[GraphDetail])
async def create_graph(
    req: CreateGraphRequest,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("graphs:write")),
) -> Result[GraphDetail]:
    item = await graph_service.create_graph(session, req)
    return Result.ok(item)


@router.post("/{graph_id}/update", response_model=Result[GraphDetail])
async def update_graph(
    graph_id: int,
    req: UpdateGraphRequest,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("graphs:write")),
) -> Result[GraphDetail]:
    item = await graph_service.update_graph(session, graph_id, req)
    return Result.ok(item)


@router.post("/{graph_id}/delete", response_model=Result[None])
async def delete_graph(
    graph_id: int,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("graphs:delete")),
) -> Result[None]:
    await graph_service.delete_graph(session, graph_id)
    return Result.ok(None)


@router.post(
    "/{graph_id}/test-run", response_model=Result[TestRunResult]
)
async def test_run(
    graph_id: int,
    req: TestRunRequest,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("graphs:execute")),
) -> Result[TestRunResult]:
    item = await graph_service.test_run(session, graph_id, req)
    return Result.ok(item)
