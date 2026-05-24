"""GraphProvider —— 把一张工作流图当作可对话 agent 执行

source='graph' 的 agent，其 AgentDef.config 由 registry 预载：
    {"graph_id": int, "spec": <published_spec dict>}

stream(ctx) 流程：
  1. ctx → graph input：{"query": <当前用户消息>, "history": [{role,content}...]}
     （LLMNode.memory_window 直接读 input["history"]，多轮记忆白送）
  2. 跑 Orchestrator(spec).run_streaming —— 引擎自管 DB session，本 provider 无需 session
  3. graph.node.* 事件翻成统一 StreamEvent：
       - 答案节点的 delta → delta{text}（token 流）
       - 节点 started/finished → step（进度可见）
       - 失败 → error
       - graph.finished → done（最终答案：流式累积优先，否则从答案节点输出提取）

答案节点：data.is_answer=true 的节点优先；否则取指向 end 的边的源节点（偏好 llm）。
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any

from loguru import logger
from pydantic import ValidationError

from chameleon.core.api.exceptions import ProviderInternalError, RegistryError
from chameleon.core.graph import GraphSpec, NodeContext
from chameleon.core.graph.engine import Orchestrator
from chameleon.providers.base.protocol import Provider
from chameleon.providers.base.types import (
    InvokeContext,
    Message,
    StreamEvent,
    StreamEventType,
)


class GraphProvider(Provider):
    """in-process 工作流引擎 provider（provider name = "graph"）"""

    name = "graph"

    async def stream(self, ctx: InvokeContext) -> AsyncIterator[StreamEvent]:
        cfg = ctx.agent_def.config
        spec_dict = cfg.get("spec")
        graph_id = cfg.get("graph_id")
        if not spec_dict:
            raise RegistryError(
                message=(
                    f"graph agent {ctx.agent_def.key} 缺 published spec —— "
                    "该工作流尚未发布？"
                )
            )
        try:
            spec = GraphSpec.model_validate(spec_dict)
        except ValidationError as e:
            raise ProviderInternalError(
                message=f"graph agent {ctx.agent_def.key} spec 非法: {e}"
            ) from e

        query, history = _extract_query_history(ctx)
        graph_input: dict[str, Any] = {"query": query, "history": history}
        answer_node_id = _resolve_answer_node(spec)

        node_ctx = NodeContext(
            request_id=ctx.request_id
            or f"graphagent-{graph_id}-{datetime.now(timezone.utc).timestamp():.0f}",
            graph_id=int(graph_id) if graph_id else 0,
            graph_run_id=0,  # in-memory，不持久化 graph_runs（trace 复用 agent call_log）
            depth=0,
            started_at=datetime.now(timezone.utc),
            extra=dict(ctx.context_vars) if ctx.context_vars else {},
        )

        logger.debug(
            "graph provider | agent={} | graph_id={} | answer_node={}",
            ctx.agent_def.key,
            graph_id,
            answer_node_id,
        )

        streamed_any = False
        answer_output: Any = None  # 答案节点 finished 时的 output
        final_output: Any = None  # graph.finished 兜底 output

        orch = Orchestrator(spec)
        async for chunk in orch.run_streaming(input=graph_input, ctx=node_ctx):
            for kind, payload in chunk.items():
                if kind == "graph.node.delta":
                    if payload.get("node_id") == answer_node_id:
                        text = payload.get("delta", "")
                        if text:
                            streamed_any = True
                            yield StreamEvent(
                                type=StreamEventType.delta, data={"text": text}
                            )
                elif kind == "graph.node.started":
                    yield StreamEvent(
                        type=StreamEventType.step,
                        data={
                            "name": payload.get("name") or payload.get("node_id"),
                            "status": "running",
                        },
                    )
                elif kind == "graph.node.finished":
                    if payload.get("node_id") == answer_node_id:
                        answer_output = payload.get("output")
                    yield StreamEvent(
                        type=StreamEventType.step,
                        data={
                            "name": payload.get("name") or payload.get("node_id"),
                            "status": "success",
                            "duration_ms": payload.get("duration_ms"),
                        },
                    )
                elif kind == "graph.node.failed":
                    err = payload.get("error") or {}
                    yield StreamEvent(
                        type=StreamEventType.error,
                        data={"message": err.get("message", "graph 节点执行失败")},
                    )
                    return
                elif kind == "graph.finished":
                    if payload.get("status") != "success":
                        err = payload.get("error") or {}
                        yield StreamEvent(
                            type=StreamEventType.error,
                            data={"message": err.get("message", "工作流执行失败")},
                        )
                        return
                    final_output = payload.get("output")

        # done：流式累积优先（answer="" 让聚合器用 delta 累积），否则提取答案节点/整图输出
        answer = (
            ""
            if streamed_any
            else _extract_answer(
                answer_output if answer_output is not None else final_output
            )
        )
        yield StreamEvent(
            type=StreamEventType.done,
            data={
                "answer": answer,
                "session_id": ctx.session_id,
                "request_id": ctx.request_id,
            },
        )


# ── helpers ───────────────────────────────────────────────


def _extract_query_history(ctx: InvokeContext) -> tuple[str, list[dict[str, str]]]:
    """从 ctx 取「当前用户消息」+「历史」喂图。

    - input: str → query=input，history=ctx.history
    - input: list[Message] → 末条为 query，其余并入 history（client-managed）
    """
    history_msgs: list[Message] = list(ctx.history)
    if isinstance(ctx.input, str):
        query = ctx.input
    else:
        msgs = ctx.input
        history_msgs = history_msgs + list(msgs[:-1])
        query = msgs[-1].text() if msgs else ""
    hist_payload = [{"role": m.role, "content": m.text()} for m in history_msgs]
    return query, hist_payload


def _resolve_answer_node(spec: GraphSpec) -> str | None:
    """判定哪个节点的输出/流是「答案」：

    1. data.is_answer=true 的节点优先；
    2. 否则取指向 end 节点的边的源节点（多个时偏好 llm）；
    3. 都没有 → None（done 时回退用 graph.finished output）。
    """
    for n in spec.nodes:
        if (n.data or {}).get("is_answer") is True:
            return n.id

    end_ids = {n.id for n in spec.nodes if n.type == "end"}
    if not end_ids:
        return None
    sources = [e.source for e in spec.edges if e.target in end_ids]
    if not sources:
        return None
    by_id = {n.id: n for n in spec.nodes}
    for sid in sources:
        node = by_id.get(sid)
        if node is not None and node.type == "llm":
            return sid
    return sources[0]


def _extract_answer(output: Any) -> str:
    """把节点/整图输出提取为答案文本。"""
    if output is None:
        return ""
    if isinstance(output, str):
        return output
    if isinstance(output, dict):
        ans = output.get("answer")
        if isinstance(ans, str) and ans:
            return ans
        try:
            return json.dumps(output, ensure_ascii=False)
        except (TypeError, ValueError):
            return str(output)
    return str(output)
