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

from chameleon.core.infra.db import AsyncSessionLocal
from chameleon.core.models import GraphNodeRun, GraphRun


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
) -> None:
    """把一次 provider 执行落成 GraphRun + 若干 GraphNodeRun（独立事务、吞异常）。"""
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
            await session.flush()
            for rec in node_records:
                nid = rec["node_id"]
                session.add(
                    GraphNodeRun(
                        graph_run_id=run.id,
                        node_id=nid,
                        node_type=rec.get("node_type") or "unknown",
                        status=rec.get("status") or "success",
                        output=_as_json_obj(rec.get("output")),
                        error=rec.get("error"),
                        request_id=f"{request_id}.{nid}",
                        started_at=rec.get("started_at"),
                        finished_at=rec.get("finished_at"),
                        duration_ms=rec.get("duration_ms"),
                    )
                )
            await session.commit()
    except Exception:  # noqa: BLE001
        logger.exception("persist provider graph run failed | graph_id={}", graph_id)
