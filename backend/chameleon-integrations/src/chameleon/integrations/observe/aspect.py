"""组件级观测切面 —— record_scope()（方案 A 的通用埋点）。

把任意能力（retriever / tool / embedding / reranker）的一次执行包成一条 call_log
观测节点：进入开 core.observe scope（嵌套 parent 链）、start→end 计时、退出经同一个
sink（record_observation）落库——归属字段从 TraceContext 取、无 scope 兜底 internal，
与 GenerationRecorder 完全一致 → 落到同一棵 trace 树。

分层：core.observe 只管 ContextVar（纯协议）；session + 落库在这里（integrations 能
import data）。任意调用方（API / 嵌入式 / Playground / 工作流 / agentkit）只要走的组件
包了 record_scope，就零 caller 代码自动出节点。
"""

from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager
from typing import Any

from loguru import logger

from chameleon.core.observe.context import (
    ObservationType,
    current_trace_context,
    observe,
)


class ObservationScope:
    """record_scope yield 的句柄：业务在 with 块内填 response_payload / 标记失败。"""

    def __init__(self, request_payload: dict[str, Any] | None) -> None:
        self.request_payload: dict[str, Any] | None = request_payload
        self.response_payload: dict[str, Any] | None = None
        self.success: bool = True
        self.code: int = 0
        self.error_message: str | None = None


@asynccontextmanager
async def record_scope(
    *,
    observation_type: str | ObservationType,
    name: str | None = None,
    request_payload: dict[str, Any] | None = None,
):
    """开一个会自动落库的观测段。

    用法：
        async with record_scope(
            observation_type=ObservationType.RETRIEVER,
            name="search_kb",
            request_payload={"query": q, "top_k": k},
        ) as scope:
            hits = await do_retrieval()
            scope.response_payload = {"citations": [...]}

    退出时：start→end 计时 + 经 sink 落一行（parent = 当前嵌套父）。异常时标记失败并
    继续抛。无 sink / 无 TraceContext 仍记（兜底 internal channel）。
    """
    scope = ObservationScope(request_payload)
    start = time.perf_counter()
    rid = uuid.uuid4().hex
    async with observe(observation_type=observation_type, name=name, request_id=rid) as obs:
        try:
            yield scope
        except Exception as e:  # noqa: BLE001
            scope.success = False
            scope.code = 500
            scope.error_message = str(e)[:500]
            raise
        finally:
            duration_ms = int((time.perf_counter() - start) * 1000)
            await _persist(
                request_id=obs.request_id,
                parent_id=obs.parent_id,
                observation_type=str(observation_type),
                duration_ms=duration_ms,
                scope=scope,
            )


async def _persist(
    *,
    request_id: str,
    parent_id: str | None,
    observation_type: str,
    duration_ms: int,
    scope: ObservationScope,
) -> None:
    # 延迟 import：避免 data.infra.db 在模块加载期被拉进来（与 GenerationRecorder 同套路）
    from chameleon.core.observe.sink import record_observation
    from chameleon.data.infra.db import AsyncSessionLocal

    tc = current_trace_context()
    try:
        async with AsyncSessionLocal() as session:
            await record_observation(
                session,
                request_id=request_id,
                app_id=(tc.app_id if tc else None) or "internal",
                agent_key=(tc.agent_key if tc else None) or "internal",
                session_id=tc.session_id if tc else None,
                stream=False,
                success=scope.success,
                code=scope.code,
                error_message=scope.error_message,
                duration_ms=duration_ms,
                request_payload=scope.request_payload,
                response_payload=scope.response_payload,
                parent_id=parent_id,
                observation_type=observation_type,
                channel=(tc.channel if tc else "internal"),
                api_key_id=tc.api_key_id if tc else None,
                end_user_id=tc.end_user_id if tc else None,
                user_id=tc.user_id if tc else None,
            )
            await session.commit()
    except Exception:  # noqa: BLE001
        logger.exception("record_scope 落库失败: {}", observation_type)
