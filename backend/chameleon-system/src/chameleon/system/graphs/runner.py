"""持久化 graph 运行器（P18.1 PR #21）

跟 test_run 的区别：
- test_run：仅 in-memory 跑 + 返结果，不写 graph_runs / graph_node_runs / call_logs（debug）
- run_graph：完整持久化链路：
    1. 建 graph_runs（pending → running）
    2. 对每节点产 graph_node_runs + call_logs（observation_type 按节点类型映射）
    3. call_logs 的 parent_id 串到 graph 根 request_id，实现 trace tree
    4. 终态更新 graph_runs（status / output / duration / node_count）

trace 串联约定：
- GraphRun.request_id = 根 trace id（observation_type='trace'）
- 每个节点的 call_log.request_id = f"{root_rid}.{node_id}"，parent_id = root_rid
- observation_type 按节点类型映射：
    llm   → generation
    kb    → retriever
    tool  → tool
    if_else / start / end / noop → span
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.api.exceptions import BusinessError, ResultCode
from chameleon.core.graph import GraphSpec, NodeContext
from chameleon.core.graph.engine import Orchestrator
from chameleon.core.models import (
    App,
    Graph,
    GraphNodeRun,
    GraphRun,
)
from chameleon.system.api_key.service import record_call

_NODE_TO_OBSERVATION_TYPE: dict[str, str] = {
    "llm": "generation",
    "kb": "retriever",
    "tool": "tool",
    "if_else": "span",
    "start": "span",
    "end": "span",
    "noop": "span",
}


_SYSTEM_APP_KEY = "system"


async def _ensure_system_app(session: AsyncSession) -> None:
    """call_logs.app_id 走 FK，admin 控制台触发的 graph run 用这个占位 app"""
    exists = (
        await session.execute(
            select(App).where(App.app_key == _SYSTEM_APP_KEY)
        )
    ).scalar_one_or_none()
    if exists is None:
        session.add(
            App(
                app_key=_SYSTEM_APP_KEY,
                name="System",
                description="平台内部 app —— admin 控制台触发的 graph run / 任务等",
                status="active",
            )
        )
        await session.flush()


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

    # 确保 call_logs.app_id FK 不被打断
    if app_id == _SYSTEM_APP_KEY:
        await _ensure_system_app(session)

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

    result = await orch.run(input=input or {}, ctx=ctx)
    finished_at = datetime.now(timezone.utc)

    # 落每节点 graph_node_runs + call_logs
    for nr in result.node_runs:
        node_rid = f"{root_rid}.{nr.node_id}"
        gn = GraphNodeRun(
            graph_run_id=run_id,
            node_id=nr.node_id,
            node_type=nr.node_type,
            status=nr.status.value,
            input=_jsonable(nr.input),
            output=_jsonable(nr.output),
            error=nr.error,
            request_id=node_rid,
            started_at=nr.started_at,
            finished_at=nr.finished_at,
            duration_ms=nr.duration_ms,
        )
        session.add(gn)

        obs_type = _NODE_TO_OBSERVATION_TYPE.get(nr.node_type, "span")
        await record_call(
            session,
            request_id=node_rid,
            app_id=app_id,
            agent_key=f"graph:{g.graph_key}",
            session_id=None,
            stream=False,
            success=nr.status.value == "success",
            code=200 if nr.status.value == "success" else 500,
            error_message=(nr.error or {}).get("message") if nr.error else None,
            duration_ms=nr.duration_ms,
            request_payload=_to_payload(nr.input),
            response_payload=_to_payload(nr.output),
            parent_id=root_rid,
            observation_type=obs_type,
        )

        # A2：LLM 节点的多轮 tool_call 串成 node 的子观测（trace tree 嵌套）
        await _record_tool_rounds(
            session,
            node_output=nr.output,
            node_rid=node_rid,
            app_id=app_id,
            agent_key=f"graph:{g.graph_key}",
        )
        # A5：parallel 节点的各 branch 串成 node 的子观测（并发分支可见）
        await _record_branch_runs(
            session,
            node_output=nr.output,
            node_rid=node_rid,
            app_id=app_id,
            agent_key=f"graph:{g.graph_key}",
        )

    # 写根 call_log（trace 根）
    await record_call(
        session,
        request_id=root_rid,
        app_id=app_id,
        agent_key=f"graph:{g.graph_key}",
        session_id=None,
        stream=False,
        success=result.status.value == "success",
        code=200 if result.status.value == "success" else 500,
        error_message=(result.error or {}).get("message") if result.error else None,
        duration_ms=result.duration_ms,
        request_payload=_to_payload(input or {}),
        response_payload=_to_payload(result.output),
        parent_id=None,
        observation_type="trace",
    )

    # 更新 graph_runs 终态
    run.status = result.status.value
    run.output = _jsonable(result.output)
    run.error = result.error
    run.finished_at = finished_at
    run.duration_ms = result.duration_ms
    run.node_count = len(result.node_runs)
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


# ── helpers ───────────────────────────────────────────────


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
