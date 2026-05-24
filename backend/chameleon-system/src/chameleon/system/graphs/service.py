"""graphs 业务 service —— CRUD + test-run

test-run 不落 graph_runs / graph_node_runs（仅 debug 用）；
正式跑 graph 走 PR #21 的 run_graph()，那个会写持久层 + 串联 trace tree。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.api.exceptions import (
    BusinessError,
    ResultCode,
    ValidationError,
)
from chameleon.core.graph import GraphSpec, NodeContext
from chameleon.core.graph.engine import Orchestrator
from chameleon.core.models import Agent, Graph, GraphRun
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

    # 校验 spec（构 GraphSpec + Orchestrator 实例化 node：data 校验也走了）
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


async def publish_graph(
    session: AsyncSession, graph_id: int
) -> GraphDetail:
    """发布 draft → freeze 当前 spec 到 published_spec；published_version += 1

    红线（plan §2 P22）：published 版本 freeze；改要新 draft → publish 重走流程。
    本函数只做 freeze 当前 draft；如要"回滚到老版本"需另开端点（v1.x）。
    """
    row = await _load(session, graph_id)
    # 简单 freeze：从 draft spec 拷贝到 published_spec
    import copy

    row.published_spec = copy.deepcopy(row.spec)
    row.published_version = (row.published_version or 0) + 1
    row.published_at = datetime.now(timezone.utc)
    await session.flush()
    await session.refresh(row)
    item = GraphDetail.model_validate(row)
    await session.commit()
    logger.info(
        "graph published | id={} | version={}",
        row.id,
        row.published_version,
    )
    return item


async def publish_as_agent(
    session: AsyncSession, graph_id: int
) -> dict[str, Any]:
    """把工作流发布并暴露成一个可对话 agent（source='graph'）。

    - 若未发布则先 freeze published_spec；
    - upsert 一个 graph-backed Agent（按 graph_id 找已有，否则以 graph_key 为 agent_key 新建）；
    - reload agent registry，使其立即可从统一端点 /v1/agents/{key}/invoke 调用。
    """
    import copy

    row = await _load(session, graph_id)
    if not row.published_spec:
        row.published_spec = copy.deepcopy(row.spec)
        row.published_version = (row.published_version or 0) + 1
        row.published_at = datetime.now(timezone.utc)
        await session.flush()

    existing = (
        await session.execute(
            select(Agent).where(
                Agent.source == "graph",
                Agent.graph_id == row.id,
                Agent.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()

    if existing is not None:
        existing.name = row.name
        existing.description = row.description
        existing.enabled = True
        agent = existing
    else:
        clash = (
            await session.execute(
                select(Agent).where(Agent.agent_key == row.graph_key)
            )
        ).scalar_one_or_none()
        if clash is not None:
            raise ValidationError(
                message=(
                    f"agent_key 已被占用: {row.graph_key}"
                    "（请改 graph_key，或先处理同名 agent）"
                )
            )
        agent = Agent(
            agent_key=row.graph_key,
            name=row.name,
            description=row.description,
            source="graph",
            graph_id=row.id,
            enabled=True,
            workspace_id=getattr(row, "workspace_id", None),
        )
        session.add(agent)

    await session.flush()
    await session.refresh(agent)
    await session.commit()

    # 让新 agent 立即生效（registry 重读 DB + 预载 published_spec）
    from chameleon.providers.base.registry import reload_agent_registry

    await reload_agent_registry()

    logger.info(
        "graph published as agent | graph_id={} | agent_key={}",
        row.id,
        agent.agent_key,
    )
    return {"agent_key": agent.agent_key, "agent_id": agent.id}


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
    orch = Orchestrator(spec)
    result = await orch.run(input=req.input, ctx=ctx)

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


async def test_run_stream(
    session: AsyncSession, graph_id: int, req: TestRunRequest
) -> AsyncIterator[dict[str, Any]]:
    """流式跑一次（SSE）—— 不落 graph_runs；边执行边发 graph.node.* 事件

    与 test_run 同样不持久化（debug 用）；区别是返回 SSE 事件流（A1）。
    spec 加载 + 校验在首次迭代时用 route session 完成（FastAPI yield 依赖在
    StreamingResponse 发完前不关 session）；节点内部各自开独立 session。
    """
    row = await _load(session, graph_id)
    spec = _validate_spec(row.spec)

    ctx = NodeContext(
        request_id=f"testrun-{row.id}-{datetime.now(timezone.utc).timestamp():.0f}",
        graph_id=row.id,
        graph_run_id=0,  # 0 = 未持久化
        depth=0,
        started_at=datetime.now(timezone.utc),
    )
    orch = Orchestrator(spec)
    async for chunk in orch.run_streaming(input=req.input, ctx=ctx):
        yield chunk


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
        Orchestrator(gs)
    except Exception as e:  # noqa: BLE001
        raise ValidationError(message=f"node config 校验失败: {e}") from e
    return gs
