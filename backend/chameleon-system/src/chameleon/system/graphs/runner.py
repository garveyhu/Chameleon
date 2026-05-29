"""持久化 graph 运行器（P18.1 PR #21）

跟 test_run 的区别：
- test_run：仅 in-memory 跑 + 返结果，不写 graph_runs / graph_node_runs / call_logs（debug）
- run_graph：完整持久化链路：
    1. 建 graph_runs（pending → running）—— 运行头 + human-input resume 锚
    2. open_trace_scope 跑引擎：节点 span + LLM generation 由引擎统一落 call_logs
       （persist_node_spans + GenerationRecorder），节点明细唯一真相源是 call_logs
    3. 补 tool / branch 子观测到 call_logs
    4. 终态更新 graph_runs + 写根 trace call_log（token/cost/model 从 generation SUM）

trace 串联约定（graph_node_runs 已删，节点明细全在 call_logs）：
- GraphRun.request_id = 根 trace id（observation_type='trace'）
- 节点 span call_log.request_id = f"{root_rid}.{node_id}"，parent_id = root_rid
- LLM generation 挂在节点 span 下（parent_id = f"{root_rid}.{node_id}"）
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.api.exceptions import BusinessError, ResultCode
from chameleon.core.graph import GraphSpec, NodeContext
from chameleon.core.graph.engine import Orchestrator
from chameleon.core.models import (
    Graph,
    GraphRun,
    HumanInputPending,
)
from chameleon.core.observe.context import TraceContext, open_trace_scope
from chameleon.system.api_key.service import (
    aggregate_generation_rollup,
    record_call,
)

# call_logs.app_id 是自由「调用方/来源标签」（无 FK）；admin 控制台触发的
# graph run 用这个占位标签兜底（keyless 调用无法锚到 key）。
_SYSTEM_APP_KEY = "system"


async def run_graph(
    session: AsyncSession,
    *,
    graph_id: int,
    input: dict[str, Any] | None = None,
    app_id: str = _SYSTEM_APP_KEY,
) -> GraphRun:
    """跑一次 graph，持久化所有结果

    Args:
        session: 复用调用方 session（route handler 注入）
        graph_id: 目标 graph id
        input: graph 入参
        app_id: call_logs.app_id，默认 'system'（admin 在控制台手动跑）

    Returns:
        GraphRun（已 commit），包含完整 status / output / node_count
    """
    g = (
        await session.execute(
            select(Graph).where(
                Graph.id == graph_id, Graph.deleted_at.is_(None)
            )
        )
    ).scalar_one_or_none()
    if g is None:
        raise BusinessError(
            ResultCode.Fail, message=f"graph 不存在: {graph_id}"
        )

    try:
        spec = GraphSpec.model_validate(g.spec)
    except Exception as e:  # noqa: BLE001
        raise BusinessError(
            ResultCode.Fail, message=f"graph spec 非法: {e}"
        ) from e

    root_rid = f"graph-{g.id}-{uuid.uuid4().hex[:12]}"
    started_at = datetime.now(timezone.utc)

    run = GraphRun(
        graph_id=g.id,
        request_id=root_rid,
        status="running",
        input=input or {},
        started_at=started_at,
    )
    session.add(run)
    await session.flush()
    await session.refresh(run)
    run_id = run.id

    # 写根 call_log（trace 根，parent_id=None）—— 先占位，结束时再 update 不现实，
    # 所以等执行完一次性写
    # 跑 executor
    ctx = NodeContext(
        request_id=root_rid,
        graph_id=g.id,
        graph_run_id=run_id,
        depth=0,
        started_at=started_at,
    )
    try:
        orch = Orchestrator(spec)
    except Exception as e:  # noqa: BLE001
        # spec 即使 model_validate 过，Orchestrator 实例化（node validate_data）也可能失败
        run.status = "failed"
        run.error = {"type": type(e).__name__, "message": str(e)[:500]}
        run.finished_at = datetime.now(timezone.utc)
        run.duration_ms = _ms(started_at, run.finished_at)
        await session.commit()
        return run

    # 开 trace scope —— 让引擎的 persist_node_spans（节点 span）+ GenerationRecorder
    # （LLM generation）按归属落 call_logs；节点 span 即 trace 树的中间层。
    async with open_trace_scope(
        TraceContext(
            request_id=root_rid,
            channel="playground",
            app_id=app_id,
            agent_key=f"graph:{g.graph_key}",
        )
    ):
        result = await orch.run(input=input or {}, ctx=ctx)

    # 节点 span / generation 已由引擎落库；这里只补 tool / branch 子观测
    await _record_node_subobservations(
        session,
        node_runs=result.node_runs,
        root_rid=root_rid,
        app_id=app_id,
        graph_key=g.graph_key,
    )
    await _finalize_run(
        session,
        run=run,
        result=result,
        spec=spec,
        root_rid=root_rid,
        app_id=app_id,
        graph_key=g.graph_key,
        request_input=input or {},
    )
    await session.commit()
    await session.refresh(run)

    logger.info(
        "graph run | id={} | graph={} | status={} | nodes={} | dur={}ms",
        run_id,
        g.graph_key,
        run.status,
        run.node_count,
        run.duration_ms,
    )
    return run


async def resume_run(
    session: AsyncSession,
    *,
    run_id: int,
    value: dict[str, Any],
    app_id: str = _SYSTEM_APP_KEY,
) -> GraphRun:
    """人工回填后从断点恢复跑（A6）

    取该 run 最新 pending 断点，以 resume_state + {node_id: value} 作 seed 重放
    已完成节点、续跑下游。可能再次暂停（下一个 human_input）或终态收尾。
    """
    run = (
        await session.execute(select(GraphRun).where(GraphRun.id == run_id))
    ).scalar_one_or_none()
    if run is None:
        raise BusinessError(ResultCode.Fail, message=f"graph_run 不存在: {run_id}")
    if run.status != "paused":
        raise BusinessError(
            ResultCode.Fail, message=f"graph_run 非暂停态（status={run.status}）不可恢复"
        )

    pending = (
        await session.execute(
            select(HumanInputPending)
            .where(
                HumanInputPending.graph_run_id == run_id,
                HumanInputPending.status == "pending",
            )
            .order_by(HumanInputPending.created_at.desc())
        )
    ).scalars().first()
    if pending is None:
        raise BusinessError(
            ResultCode.Fail, message=f"graph_run {run_id} 无待回填断点"
        )

    g = (
        await session.execute(select(Graph).where(Graph.id == run.graph_id))
    ).scalar_one_or_none()
    if g is None:
        raise BusinessError(ResultCode.Fail, message="关联 graph 不存在")
    spec = GraphSpec.model_validate(g.spec)

    seed: dict[str, Any] = dict(pending.resume_state or {})
    seed[pending.node_id] = value

    ctx = NodeContext(
        request_id=run.request_id,
        graph_id=run.graph_id,
        graph_run_id=run.id,
        depth=0,
        started_at=run.started_at or datetime.now(timezone.utc),
    )
    async with open_trace_scope(
        TraceContext(
            request_id=run.request_id,
            channel="playground",
            app_id=app_id,
            agent_key=f"graph:{g.graph_key}",
        )
    ):
        result = await Orchestrator(spec).run(
            input=run.input, ctx=ctx, seed_outputs=seed
        )

    # 标记断点已回填
    pending.status = "resolved"
    pending.value = value
    pending.resolved_at = datetime.now(timezone.utc)

    # 只补新跑节点的 tool/branch 子观测（节点 span / generation 引擎已落）
    await _record_node_subobservations(
        session,
        node_runs=result.node_runs,
        root_rid=run.request_id,
        app_id=app_id,
        graph_key=g.graph_key,
        skip=set(seed.keys()),
    )
    await _finalize_run(
        session,
        run=run,
        result=result,
        spec=spec,
        root_rid=run.request_id,
        app_id=app_id,
        graph_key=g.graph_key,
        request_input=run.input,
    )
    await session.commit()
    await session.refresh(run)
    logger.info(
        "graph resume | id={} | node={} | status={}",
        run.id,
        pending.node_id,
        run.status,
    )
    return run


# ── helpers ───────────────────────────────────────────────


async def _record_node_subobservations(
    session: AsyncSession,
    *,
    node_runs: list,
    root_rid: str,
    app_id: str,
    graph_key: str,
    skip: set[str] = frozenset(),  # type: ignore[assignment]
) -> None:
    """补落节点的 tool / branch 子观测到 call_logs

    节点 span 行 + LLM generation 行已由引擎（persist_node_spans + GenerationRecorder）
    落库；这里只补「LLM 节点的工具调用」「parallel 节点的并发分支」两类子观测，
    parent_id 挂到节点 span（f"{root}.{node_id}"）下。

    skip 里的 node_id 跳过（resume 时已在之前 run 落过，避免重复）。
    """
    for nr in node_runs:
        if nr.node_id in skip:
            continue
        node_rid = f"{root_rid}.{nr.node_id}"
        await _record_tool_rounds(
            session,
            node_output=nr.output,
            node_rid=node_rid,
            app_id=app_id,
            agent_key=f"graph:{graph_key}",
        )
        await _record_branch_runs(
            session,
            node_output=nr.output,
            node_rid=node_rid,
            app_id=app_id,
            agent_key=f"graph:{graph_key}",
        )


async def _finalize_run(
    session: AsyncSession,
    *,
    run: GraphRun,
    result: Any,
    spec: GraphSpec,
    root_rid: str,
    app_id: str,
    graph_key: str,
    request_input: dict,
) -> None:
    """收尾：暂停 → 落 pending 断点 + status=paused；终态 → 根 trace + 终态字段"""
    if result.status.value == "paused":
        await _persist_pending(session, run=run, result=result, spec=spec)
        run.status = "paused"
        run.node_count = len(result.node_runs)
        return

    # 终态（success / failed）：写根 call_log（trace 根）+ 更新 graph_run
    # 根行 token/cost/model 从 generation 子行聚合补回（引擎已落 generation）
    p, c, t, cost, model = await aggregate_generation_rollup(session, root_rid)
    await record_call(
        session,
        request_id=root_rid,
        app_id=app_id,
        agent_key=f"graph:{graph_key}",
        session_id=None,
        stream=False,
        success=result.status.value == "success",
        code=200 if result.status.value == "success" else 500,
        error_message=(result.error or {}).get("message") if result.error else None,
        duration_ms=result.duration_ms,
        prompt_tokens=p,
        completion_tokens=c,
        total_tokens=t,
        request_payload=_to_payload(request_input),
        response_payload=_to_payload(result.output),
        parent_id=None,
        observation_type="trace",
        model_code=model,
        cost_usd=cost,
    )
    run.status = result.status.value
    run.output = _jsonable(result.output)
    run.error = result.error
    run.finished_at = datetime.now(timezone.utc)
    run.duration_ms = result.duration_ms
    run.node_count = len(result.node_runs)


async def _persist_pending(
    session: AsyncSession,
    *,
    run: GraphRun,
    result: Any,
    spec: GraphSpec,
) -> None:
    """落 human_input_pending 断点行（resume_state = 已完成节点输出快照）"""
    pending = result.pending or {}
    node_id = pending.get("node_id")
    timeout_at = None
    node_spec = spec.find_node(node_id) if node_id else None
    if node_spec is not None:
        ts = node_spec.data.get("timeout_seconds")
        if isinstance(ts, int) and ts > 0:
            timeout_at = datetime.now(timezone.utc) + timedelta(seconds=ts)
    session.add(
        HumanInputPending(
            graph_run_id=run.id,
            node_id=node_id or "",
            status="pending",
            prompt=pending.get("prompt"),
            input_schema=pending.get("schema"),
            node_input=_to_payload(pending.get("node_input")),
            resume_state=_jsonable(result.node_outputs),
            timeout_at=timeout_at,
        )
    )


async def _record_tool_rounds(
    session: AsyncSession,
    *,
    node_output: Any,
    node_rid: str,
    app_id: str,
    agent_key: str,
) -> None:
    """把 LLM 节点 output.tool_rounds 里的每次工具调用记成 node 的子观测

    parent_id = node_rid（LLM 节点的 generation 观测），observation_type='tool'，
    使 trace tree 呈现：graph → llm(generation) → tool / tool（多轮嵌套）。
    output 无 tool_rounds（非 LLM 节点 / 未用工具）时直接返回，零开销。
    """
    if not isinstance(node_output, dict):
        return
    rounds = node_output.get("tool_rounds")
    if not isinstance(rounds, list) or not rounds:
        return

    for ri, rnd in enumerate(rounds):
        results = rnd.get("tool_results") if isinstance(rnd, dict) else None
        if not isinstance(results, list):
            continue
        for ti, rec in enumerate(results):
            if not isinstance(rec, dict):
                continue
            result = rec.get("result") or {}
            ok = bool(result.get("ok", True)) if isinstance(result, dict) else True
            await record_call(
                session,
                request_id=f"{node_rid}.tool.{ri}.{ti}",
                app_id=app_id,
                agent_key=agent_key,
                session_id=None,
                stream=False,
                success=ok,
                code=200 if ok else 500,
                error_message=(
                    result.get("error") if isinstance(result, dict) else None
                ),
                duration_ms=0,
                request_payload=_to_payload(
                    {"name": rec.get("name"), "args": rec.get("args")}
                ),
                response_payload=_to_payload(result),
                parent_id=node_rid,
                observation_type="tool",
            )


async def _record_branch_runs(
    session: AsyncSession,
    *,
    node_output: Any,
    node_rid: str,
    app_id: str,
    agent_key: str,
) -> None:
    """把 parallel 节点 output.branch_runs 的每条分支记成 node 的子观测

    parent_id = node_rid，observation_type='span'，duration_ms = 分支实测时长，
    使 trace tree 呈现并发分支。无 branch_runs（非 parallel 节点）时零开销。
    """
    if not isinstance(node_output, dict):
        return
    runs = node_output.get("branch_runs")
    if not isinstance(runs, list) or not runs:
        return

    for bi, br in enumerate(runs):
        if not isinstance(br, dict):
            continue
        ok = bool(br.get("ok", True))
        await record_call(
            session,
            request_id=f"{node_rid}.branch.{br.get('key', bi)}",
            app_id=app_id,
            agent_key=agent_key,
            session_id=None,
            stream=False,
            success=ok,
            code=200 if ok else 500,
            error_message=(br.get("error") or {}).get("message")
            if isinstance(br.get("error"), dict)
            else None,
            duration_ms=int(br.get("duration_ms") or 0),
            request_payload={"key": br.get("key")},
            response_payload={
                "started_offset_ms": br.get("started_offset_ms"),
                "duration_ms": br.get("duration_ms"),
            },
            parent_id=node_rid,
            observation_type="span",
        )


def _ms(t0: datetime, t1: datetime) -> int:
    return int((t1 - t0).total_seconds() * 1000)


def _jsonable(v: Any) -> Any:
    """确保 v 可序列化到 JSONB；非 dict/list/scalar 转 str"""
    if v is None or isinstance(v, (bool, int, float, str)):
        return v
    if isinstance(v, dict):
        return {str(k): _jsonable(val) for k, val in v.items()}
    if isinstance(v, list):
        return [_jsonable(x) for x in v]
    # pydantic / 其它 → 试 model_dump，否则 str
    if hasattr(v, "model_dump"):
        try:
            return v.model_dump()
        except Exception:  # noqa: BLE001
            return str(v)
    return str(v)


def _to_payload(v: Any) -> dict | None:
    """call_logs.{request,response}_payload 必须是 dict | None"""
    j = _jsonable(v)
    if j is None:
        return None
    if isinstance(j, dict):
        return j
    return {"value": j}
