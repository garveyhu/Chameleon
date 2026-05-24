"""graphs HTTP 路由（/v1/admin/graphs）"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.api.response import Result
from chameleon.core.api.sse import sse_response
from chameleon.core.infra.db import get_session
from chameleon.system.auth.dependencies import require_permission
from chameleon.system.graphs import runner as graph_runner
from chameleon.system.graphs import service as graph_service
from chameleon.system.graphs.schemas import (
    CreateGraphRequest,
    GraphDetail,
    GraphItem,
    GraphRunDetail,
    GraphRunItem,
    GraphRunRequest,
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
    "/{graph_id}/publish", response_model=Result[GraphDetail]
)
async def publish_graph(
    graph_id: int,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("graphs:write")),
) -> Result[GraphDetail]:
    """P22.3：发布 draft → freeze published_spec；published_version += 1"""
    item = await graph_service.publish_graph(session, graph_id)
    return Result.ok(item)


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


@router.post("/{graph_id}/test-run/stream")
async def test_run_stream(
    graph_id: int,
    req: TestRunRequest,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("graphs:execute")),
):
    """SSE 流式 Test Run（A1）：边执行边推 graph.node.started/finished/failed

    不落 graph_runs（debug 用）；wire 事件见 SSEEventKind 的 GRAPH_* 成员。
    """
    return sse_response(
        graph_service.test_run_stream(session, graph_id, req),
        log_label="graphs:test-run-stream",
    )


@router.post("/{graph_id}/run", response_model=Result[GraphRunDetail])
async def run_graph(
    graph_id: int,
    req: GraphRunRequest,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("graphs:execute")),
) -> Result[GraphRunDetail]:
    """正式跑（持久化 graph_runs / graph_node_runs / call_logs，串到 trace tree）"""
    run = await graph_runner.run_graph(
        session, graph_id=graph_id, input=req.input
    )
    return Result.ok(GraphRunDetail.model_validate(run))


@router.get("/{graph_id}/runs", response_model=Result[list[GraphRunItem]])
async def list_runs(
    graph_id: int,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("graphs:read")),
) -> Result[list[GraphRunItem]]:
    items = await graph_service.list_runs(session, graph_id)
    return Result.ok(items)


@router.get("/runs/{run_id}", response_model=Result[GraphRunDetail])
async def get_run(
    run_id: int,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("graphs:read")),
) -> Result[GraphRunDetail]:
    item = await graph_service.get_run(session, run_id)
    return Result.ok(item)
