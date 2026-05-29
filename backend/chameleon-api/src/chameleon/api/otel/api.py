"""OTLP HTTP/JSON 路由 —— P22.2 PR #73

挂点：POST /v1/otel/v1/traces

红线（plan §2 P22）：
- ⛔ 任何写入必须 app_id 校验（current_app dep）；不允许匿名上报
- ⛔ 单批 ≤ 5000 span（防 OOM）
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.api.otel.converter import (
    convert_and_persist_span,
    count_spans,
)
from chameleon.api.otel.schemas import (
    ExportTraceServiceRequest,
    ExportTraceServiceResponse,
)
from chameleon.data.infra.auth import CurrentApp, current_app
from chameleon.data.infra.db import get_session

router = APIRouter(prefix="/v1/otel", tags=["otel"])

#: 单批 spans 上限
MAX_SPANS_PER_REQUEST = 5000


@router.post("/v1/traces", response_model=ExportTraceServiceResponse)
async def export_traces(
    req: ExportTraceServiceRequest,
    session: AsyncSession = Depends(get_session),
    app: CurrentApp = Depends(current_app),
) -> ExportTraceServiceResponse:
    """OTLP/JSON traces 摄入

    标准 path: /v1/traces；本服务前缀 /v1/otel，故完整路径 /v1/otel/v1/traces。
    """
    total_spans = count_spans(req.resourceSpans)
    if total_spans > MAX_SPANS_PER_REQUEST:
        raise HTTPException(
            status_code=413,
            detail=f"too many spans: {total_spans} > {MAX_SPANS_PER_REQUEST}",
        )
    if total_spans == 0:
        return ExportTraceServiceResponse()

    persisted = 0
    rejected = 0
    for rs in req.resourceSpans:
        for ss in rs.scopeSpans:
            scope_name = ss.scope.name if ss.scope else None
            for span in ss.spans:
                try:
                    await convert_and_persist_span(
                        session,
                        span,
                        resource=rs.resource,
                        scope_name=scope_name,
                        app_id=app.app_id,
                    )
                    persisted += 1
                except Exception:
                    rejected += 1
                    # 单 span 失败不阻塞整批；converter 内部已 log
                    continue

    await session.commit()
    logger.info(
        "otel ingest | app={} | total={} | ok={} | rejected={}",
        app.app_id,
        total_spans,
        persisted,
        rejected,
    )
    if rejected > 0:
        return ExportTraceServiceResponse(
            partialSuccess={
                "rejectedSpans": str(rejected),
                "errorMessage": "see backend logs",
            }
        )
    return ExportTraceServiceResponse()
