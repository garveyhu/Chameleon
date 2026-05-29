"""scores HTTP 路由 (/v1/admin/scores)

仅 admin 端，widget feedback 由 chameleon-api 的 embed 模块代理。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.api.response import Result
from chameleon.data.infra.db import get_session
from chameleon.system.auth.dependencies import require_permission
from chameleon.system.scores import service as score_service
from chameleon.system.scores.schemas import CreateScoreRequest, ScoreItem

router = APIRouter(prefix="/v1/admin/scores", tags=["admin:scores"])


@router.get("", response_model=Result[list[ScoreItem]])
async def list_scores(
    call_log_id: str | None = Query(default=None),
    trace_id: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("call_logs:read")),
) -> Result[list[ScoreItem]]:
    """按 call_log_id 或 trace_id 过滤；二者必传其一"""
    if call_log_id:
        items = await score_service.list_scores_by_call(session, call_log_id)
    elif trace_id:
        items = await score_service.list_scores_by_trace(session, trace_id)
    else:
        items = []
    return Result.ok(items)


@router.post("", response_model=Result[ScoreItem])
async def create_score(
    req: CreateScoreRequest,
    session: AsyncSession = Depends(get_session),
    _: object = Depends(require_permission("call_logs:write")),
) -> Result[ScoreItem]:
    """admin 主动写 score（标注 / 人工评分）"""
    item = await score_service.create_score(session, req)
    return Result.ok(item)
