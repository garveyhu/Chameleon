"""把 graph-agent（provider）跑出来的执行轨迹补落 graph_runs / graph_node_runs

GraphRunner（chameleon-system）只覆盖 admin 控制台「运行」端点的持久化。graph 作为
agent 经 provider.stream 跑时（对话调试 / 公开 Web App / 已发布 agent / OpenAI 兼容
端点）原先 graph_run_id=0、不落库，导致编辑器「日志 / 监测」始终无数据。

本模块用独立短事务把流式执行收集到的节点轨迹补落 graph 视图所需的两张表；trace
（call_logs 根观测）已由 agent 调用层（embed / api_key）写，这里不重复。

持久化失败只记日志、绝不影响对话流——日志缺一条远没有把用户对话打断严重。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from loguru import logger

from chameleon.data.infra.db import AsyncSessionLocal
from chameleon.data.models import GraphRun, HumanInputPending


def _as_json_obj(v: Any) -> dict | None:
    """graph_runs/graph_node_runs 的 output 列是 JSON dict | None；非 dict 包一层。"""
    if v is None:
        return None
    if isinstance(v, dict):
        return v
    return {"value": v}


async def persist_provider_run(
    *,
    graph_id: int,
    request_id: str,
    session_id: str | None,
    graph_input: dict[str, Any],
    started_at: datetime,
    finished_at: datetime,
    status: str,
    output: Any,
    error: dict[str, Any] | None,
    node_records: list[dict[str, Any]],
    pending: dict[str, Any] | None = None,
    pending_resume_state: Any = None,
    pending_timeout_at: datetime | None = None,
) -> None:
    """把一次 provider 执行落成 GraphRun 运行头（独立事务、吞异常）。

    节点明细（span + LLM generation）由引擎统一落 call_logs，不在这里重复。

    status="paused" 时同步落 HumanInputPending 断点行（与 GraphRunner 的
    _persist_pending 同语义）——没有断点行，运营「回填续跑」必失败、超时
    清扫也永远扫不到，paused run 会成为不可恢复的死端。
    """
    try:
        async with AsyncSessionLocal() as session:
            run = GraphRun(
                graph_id=graph_id,
                request_id=request_id,
                session_id=session_id,
                status=status,
                input=graph_input or {},
                output=_as_json_obj(output),
                error=error,
                started_at=started_at,
                finished_at=finished_at,
                duration_ms=int((finished_at - started_at).total_seconds() * 1000),
                node_count=len(node_records),
            )
            session.add(run)
            if status == "paused" and pending:
                await session.flush()  # 拿 run.id 做外键
                session.add(
                    HumanInputPending(
                        graph_run_id=run.id,
                        node_id=str(pending.get("node_id") or ""),
                        status="pending",
                        prompt=pending.get("prompt"),
                        input_schema=pending.get("schema"),
                        node_input=_as_json_obj(pending.get("node_input")),
                        resume_state=pending_resume_state,
                        timeout_at=pending_timeout_at,
                    )
                )
            # 节点明细（span + generation）由引擎统一落 call_logs（persist_node_spans
            # + GenerationRecorder），不再单独落 graph_node_runs —— call_logs 是唯一真相源。
            await session.commit()
    except Exception:  # noqa: BLE001
        logger.exception("persist provider graph run failed | graph_id={}", graph_id)
