"""graphs 业务 service —— CRUD + test-run

test-run 不落 graph_runs / graph_node_runs（仅 debug 用）；
正式跑 graph 走 PR #21 的 run_graph()，那个会写持久层 + 串联 trace tree。
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.api.exceptions import (
    BusinessError,
    ResultCode,
    ValidationError,
)
from chameleon.core.graph import GraphExecutor, GraphSpec, NodeContext
from chameleon.core.models import Graph, GraphRun
from chameleon.system.graphs.schemas import (
    CreateGraphRequest,
    GraphDetail,
    GraphItem,
    GraphRunDetail,
    GraphRunItem,
    NodeRunItem,
    TestRunRequest,
    TestRunResult,
    UpdateGraphRequest,
)


async def list_graphs(session: AsyncSession) -> list[GraphItem]:
    rows = (
        (
            await session.execute(
                select(Graph)
                .where(Graph.deleted_at.is_(None))
                .order_by(Graph.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return [GraphItem.model_validate(r) for r in rows]


async def get_graph(session: AsyncSession, graph_id: int) -> GraphDetail:
    row = await _load(session, graph_id)
    return GraphDetail.model_validate(row)


async def create_graph(
    session: AsyncSession, req: CreateGraphRequest
) -> GraphDetail:
    # 验 graph_key 唯一（防 DB UNIQUE 报错更清晰）
    dup = (
        await session.execute(
            select(Graph.id).where(Graph.graph_key == req.graph_key)
        )
    ).scalar_one_or_none()
    if dup is not None:
        raise ValidationError(message=f"graph_key 已存在: {req.graph_key}")

    # 校验 spec（构 GraphSpec + GraphExecutor 实例化 node：data 校验也走了）
    _validate_spec(req.spec)

    row = Graph(
        graph_key=req.graph_key,
        name=req.name,
        description=req.description,
        spec=req.spec,
        enabled=True,
    )
    session.add(row)
    await session.flush()
    await session.refresh(row)
    item = GraphDetail.model_validate(row)
    await session.commit()
    return item


async def update_graph(
    session: AsyncSession, graph_id: int, req: UpdateGraphRequest
) -> GraphDetail:
    row = await _load(session, graph_id)
    if req.name is not None:
        row.name = req.name
    if req.description is not None:
        row.description = req.description
    if req.spec is not None:
        _validate_spec(req.spec)
        row.spec = req.spec
    if req.enabled is not None:
        row.enabled = req.enabled
    await session.flush()
    await session.refresh(row)
    item = GraphDetail.model_validate(row)
    await session.commit()
    return item


async def delete_graph(session: AsyncSession, graph_id: int) -> None:
    """软删 —— graph_runs 历史保留（cascade 不触发，因为软删不删行）"""
    row = await _load(session, graph_id)
    row.deleted_at = datetime.now(timezone.utc)
    await session.flush()
    await session.commit()


async def test_run(
    session: AsyncSession, graph_id: int, req: TestRunRequest
) -> TestRunResult:
    """跑一次但不落 graph_runs 表（仅 debug；正式 run 用 PR #21）"""
    row = await _load(session, graph_id)
    spec = _validate_spec(row.spec)

    ctx = NodeContext(
        request_id=f"testrun-{row.id}-{datetime.now(timezone.utc).timestamp():.0f}",
        graph_id=row.id,
        graph_run_id=0,  # 0 = 未持久化
        depth=0,
        started_at=datetime.now(timezone.utc),
    )
    executor = GraphExecutor(spec)
    result = await executor.run(input=req.input, ctx=ctx)

    return TestRunResult(
        status=result.status.value,
        output=result.output,
        error=result.error,
        duration_ms=result.duration_ms,
        node_runs=[
            NodeRunItem(
                node_id=r.node_id,
                node_type=r.node_type,
                status=r.status.value,
                input=r.input,
                output=r.output,
                error=r.error,
                duration_ms=r.duration_ms,
            )
            for r in result.node_runs
        ],
    )


# ── helpers ───────────────────────────────────────────────


async def _load(session: AsyncSession, graph_id: int) -> Graph:
    row = (
        await session.execute(
            select(Graph).where(
                Graph.id == graph_id, Graph.deleted_at.is_(None)
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise BusinessError(
            ResultCode.Fail, message=f"graph 不存在: {graph_id}"
        )
    return row


async def list_runs(
    session: AsyncSession, graph_id: int, limit: int = 50
) -> list[GraphRunItem]:
    """按 graph_id 列 runs（最新在前）"""
    rows = (
        (
            await session.execute(
                select(GraphRun)
                .where(GraphRun.graph_id == graph_id)
                .order_by(GraphRun.created_at.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return [GraphRunItem.model_validate(r) for r in rows]


async def get_run(session: AsyncSession, run_id: int) -> GraphRunDetail:
    row = (
        await session.execute(select(GraphRun).where(GraphRun.id == run_id))
    ).scalar_one_or_none()
    if row is None:
        raise BusinessError(
            ResultCode.Fail, message=f"graph_run 不存在: {run_id}"
        )
    return GraphRunDetail.model_validate(row)


def _validate_spec(spec: dict) -> GraphSpec:
    """spec dict → GraphSpec（结构 + 实例化 node 校验 data）"""
    try:
        gs = GraphSpec.model_validate(spec)
    except Exception as e:  # noqa: BLE001
        raise ValidationError(message=f"spec 非法: {e}") from e
    try:
        # 实例化所有 node 跑 validate_data
        GraphExecutor(gs)
    except Exception as e:  # noqa: BLE001
        raise ValidationError(message=f"node config 校验失败: {e}") from e
    return gs
