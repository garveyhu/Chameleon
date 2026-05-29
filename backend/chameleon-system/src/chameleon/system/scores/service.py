"""scores 业务 service —— append-only 写 + 按 call_log/trace 列表读

写多读少：
- 写：widget 反馈 / admin 标注，单次 INSERT，不带事务嵌套
- 读：trace drawer 展示该 trace 上所有 score
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.api.exceptions import BusinessError, ResultCode
from chameleon.data.models import CallLog, Score
from chameleon.system.scores.schemas import (
    CreateScoreRequest,
    FeedbackRequest,
    ScoreItem,
)


async def create_score(
    session: AsyncSession, req: CreateScoreRequest
) -> ScoreItem:
    """admin / eval 主动写 score

    校验 call_log_id 必须真实存在（防止脏写）。
    """
    rid_exists = (
        await session.execute(
            select(CallLog.id).where(CallLog.request_id == req.call_log_id)
        )
    ).scalar_one_or_none()
    if rid_exists is None:
        raise BusinessError(
            ResultCode.AgentNotFound,
            message=f"call_log_id 不存在: {req.call_log_id}",
        )

    s = Score(
        call_log_id=req.call_log_id,
        trace_id=req.trace_id,
        name=req.name,
        value=req.value,
        string_value=req.string_value,
        data_type=req.data_type,
        source=req.source,
        comment=req.comment,
    )
    session.add(s)
    await session.flush()
    await session.refresh(s)
    item = ScoreItem.model_validate(s)
    await session.commit()
    return item


async def record_feedback(
    session: AsyncSession,
    req: FeedbackRequest,
    *,
    source: str = "feedback",
) -> ScoreItem:
    """widget 反馈入口 —— trace_id 即 call_log.request_id（trace 根）

    数据类型自动推断；feedback 默认归在 trace 根 call_log 上
    （不区分子 observation，简化 widget 端逻辑）。
    """
    rid_exists = (
        await session.execute(
            select(CallLog.id).where(CallLog.request_id == req.trace_id)
        )
    ).scalar_one_or_none()
    if rid_exists is None:
        raise BusinessError(
            ResultCode.AgentNotFound,
            message=f"trace_id 不存在: {req.trace_id}",
        )

    data_type = "numeric" if req.value is not None else "categorical"
    s = Score(
        call_log_id=req.trace_id,
        trace_id=req.trace_id,
        name=req.name,
        value=req.value,
        string_value=req.string_value,
        data_type=data_type,
        source=source,
        comment=req.comment,
    )
    session.add(s)
    await session.flush()
    await session.refresh(s)
    item = ScoreItem.model_validate(s)
    await session.commit()
    return item


async def list_scores_by_call(
    session: AsyncSession, call_log_id: str
) -> list[ScoreItem]:
    """按 call_log.request_id 列出 scores（最新在前）"""
    rows = (
        await session.execute(
            select(Score)
            .where(Score.call_log_id == call_log_id)
            .order_by(Score.created_at.desc())
        )
    ).scalars().all()
    return [ScoreItem.model_validate(r) for r in rows]


async def list_scores_by_trace(
    session: AsyncSession, trace_id: str
) -> list[ScoreItem]:
    """按 trace 根 id 列出 scores（含子 observation 上的）"""
    rows = (
        await session.execute(
            select(Score)
            .where(Score.trace_id == trace_id)
            .order_by(Score.created_at.desc())
        )
    ).scalars().all()
    return [ScoreItem.model_validate(r) for r in rows]
