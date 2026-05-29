"""Agent ↔ KB 关联服务（P16-C5）

读：返关联的 KB list。
写：全量替换 agent 的关联 kb_ids（先删旧，再批量插）。
"""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.api.exceptions import (
    BusinessError,
    ResultCode,
    ValidationError,
)
from chameleon.data.models import Agent, AgentKbLink, KnowledgeBase


async def _get_agent(session: AsyncSession, agent_id: int) -> Agent:
    a = (
        await session.execute(
            select(Agent).where(Agent.id == agent_id, Agent.deleted_at.is_(None))
        )
    ).scalar_one_or_none()
    if a is None:
        raise BusinessError(
            ResultCode.AgentNotFound, message=f"agent 不存在: {agent_id}"
        )
    return a


async def list_linked_kbs(
    session: AsyncSession, *, agent_id: int
) -> list[KnowledgeBase]:
    await _get_agent(session, agent_id)
    rows = (
        (
            await session.execute(
                select(KnowledgeBase)
                .join(AgentKbLink, AgentKbLink.kb_id == KnowledgeBase.id)
                .where(
                    AgentKbLink.agent_id == agent_id,
                    KnowledgeBase.deleted_at.is_(None),
                )
                .order_by(KnowledgeBase.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


async def replace_linked_kbs(
    session: AsyncSession, *, agent_id: int, kb_ids: list[int]
) -> list[KnowledgeBase]:
    """全量替换：删旧 link → 校验 kb 都存在且未删 → 插入新 link → 返新 KB list。"""
    await _get_agent(session, agent_id)
    dedup_ids = list(dict.fromkeys(kb_ids))  # 保序去重
    if dedup_ids:
        rows = (
            (
                await session.execute(
                    select(KnowledgeBase.id).where(
                        KnowledgeBase.id.in_(dedup_ids),
                        KnowledgeBase.deleted_at.is_(None),
                    )
                )
            )
            .scalars()
            .all()
        )
        existing = set(rows)
        missing = [k for k in dedup_ids if k not in existing]
        if missing:
            raise ValidationError(message=f"kb 不存在或已删除: {missing}")
    # 删旧
    await session.execute(
        delete(AgentKbLink).where(AgentKbLink.agent_id == agent_id)
    )
    # 插新
    for kid in dedup_ids:
        session.add(AgentKbLink(agent_id=agent_id, kb_id=kid))
    await session.flush()
    return await list_linked_kbs(session, agent_id=agent_id)
