"""graph 节点轨迹 → call_logs span 行

把 Orchestrator 跑出的 node_runs 落成 call_logs 的 span 观测行，使一次 graph 执行的
trace 树长成 LangSmith 形状：

    根 trace（agent 调用层落）
      └─ 节点 span（本模块落，request_id = f"{root}.{node_id}"）
           └─ LLM generation（GenerationRecorder 落，parent_id = 节点 span id）

节点执行期间 Orchestrator 用 observe(request_id=f"{root}.{node_id}") 把 _CURRENT_OBS_ID
设成节点 span id，于是 GenerationRecorder 落 generation 时自动认它当 parent —— 二者用
同一套确定性 id 串起来，无需 FK（call_logs.parent_id 是裸字符串）。

归属（app_id/agent_key/channel/...）从 current_trace_context() 取；**没开 trace scope
就直接跳过**（纯 orchestrator 单测不碰 DB / 不需要 system 层）。

落库经 core.observe.sink.record_observation（可注入 sink，由上层 app 注册具体写库实现），
core 不再 import chameleon.system —— 消除 core→system 上行依赖。
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from chameleon.core.observe.context import (
    ObservationType,
    current_trace_context,
)

_PAYLOAD_TRUNCATE = 4000

# 节点类型 → observation_type：kb/tool 给语义类型；其余（含 llm —— 真正的 LLM 调用由
# GenerationRecorder 落 generation 嵌在 span 下，节点壳本身是 span）一律 span。
_NODE_TO_OBSERVATION_TYPE: dict[str, str] = {
    "kb": ObservationType.RETRIEVER.value,
    "tool": ObservationType.TOOL.value,
}


def _payload(value: Any, key: str) -> dict | None:
    """把节点 input/output 包成 call_log payload dict（截断防爆）。"""
    if value is None:
        return None
    text = value if isinstance(value, str) else repr(value)
    return {key: text[:_PAYLOAD_TRUNCATE]}


async def persist_node_spans(*, root_request_id: str, node_runs: list[Any]) -> None:
    """把 node_runs 落成 call_logs span 行（嵌在 root trace 下）。

    Args:
        root_request_id: 根 trace 的 request_id（节点 span 的 parent_id）
        node_runs: list[NodeRunResult]（Orchestrator RunResult.node_runs）

    无 trace scope 时直接 return（不写库）。失败只记日志，绝不打断对话流。
    """
    tc = current_trace_context()
    if tc is None or not node_runs:
        return

    from chameleon.core.observe.sink import record_observation
    from chameleon.data.infra.db import AsyncSessionLocal

    try:
        async with AsyncSessionLocal() as session:
            for nr in node_runs:
                node_id = getattr(nr, "node_id", None)
                if not node_id:
                    continue
                node_type = getattr(nr, "node_type", "") or ""
                status = getattr(nr, "status", None)
                success = getattr(status, "value", str(status)) == "success"
                err = getattr(nr, "error", None)
                # request_payload 带上 node_id/node_type —— 编辑器「日志」详情从
                # call_logs span 反查节点时用（graph_node_runs 删除后唯一来源）。
                req_payload = _payload(getattr(nr, "input", None), "input") or {}
                req_payload["node_id"] = node_id
                req_payload["node_type"] = node_type
                await record_observation(
                    session,
                    request_id=f"{root_request_id}.{node_id}",
                    app_id=tc.app_id or "internal",
                    agent_key=tc.agent_key or "internal",
                    session_id=tc.session_id,
                    stream=False,
                    success=success,
                    code=0 if success else 500,
                    error_message=(
                        f"{err.get('type')}: {err.get('message')}"
                        if isinstance(err, dict)
                        else None
                    ),
                    duration_ms=getattr(nr, "duration_ms", 0) or 0,
                    request_payload=req_payload,
                    response_payload=_payload(getattr(nr, "output", None), "output"),
                    parent_id=root_request_id,
                    observation_type=_NODE_TO_OBSERVATION_TYPE.get(
                        node_type, ObservationType.SPAN.value
                    ),
                    channel=tc.channel,
                    api_key_id=tc.api_key_id,
                    end_user_id=tc.end_user_id,
                    user_id=tc.user_id,
                )
            await session.commit()
    except Exception:  # noqa: BLE001
        logger.exception(
            "persist node spans failed | root_request_id={}", root_request_id
        )
