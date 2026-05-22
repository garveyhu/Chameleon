"""abilities 业务 service —— CRUD + 关联 channel/provider 展示

CRUD 范畴 + 唯一约束维护；路由解析见 chameleon.core.routing.router。
"""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.api.exceptions import (
    BusinessError,
    ResultCode,
    ValidationError,
)
from chameleon.core.models import Ability, Channel, Provider
from chameleon.system.abilities.schemas import (
    AbilityItem,
    CreateAbilityRequest,
    UpdateAbilityRequest,
)


async def list_abilities(
    session: AsyncSession,
    *,
    model_code: str | None = None,
    group_id: int | None = None,
    channel_id: int | None = None,
) -> list[AbilityItem]:
    """列出 abilities，join channel + provider 展示

    group_id 过滤语义：
    - None（不传）→ 不过滤，全部返
    - 0 → 视为 "查全局 ability"（NULL group_id）
    - >0 → 精确匹配
    """
    stmt = (
        select(Ability, Channel, Provider.code)
        .join(Channel, Ability.channel_id == Channel.id)
        .join(Provider, Channel.provider_id == Provider.id)
        .where(Channel.deleted_at.is_(None))
        .order_by(
            Ability.model_code.asc(),
            Ability.priority.desc(),
            Ability.id.asc(),
        )
    )
    if model_code is not None:
        stmt = stmt.where(Ability.model_code == model_code)
    if group_id is not None:
        if group_id == 0:
            stmt = stmt.where(Ability.group_id.is_(None))
        else:
            stmt = stmt.where(Ability.group_id == group_id)
    if channel_id is not None:
        stmt = stmt.where(Ability.channel_id == channel_id)

    rows = (await session.execute(stmt)).all()
    return [_row_to_item(a, ch, provider_code) for a, ch, provider_code in rows]


async def create_ability(
    session: AsyncSession, req: CreateAbilityRequest
) -> AbilityItem:
    # 验 channel 存在且未删
    ch = (
        await session.execute(
            select(Channel).where(
                Channel.id == req.channel_id, Channel.deleted_at.is_(None)
            )
        )
    ).scalar_one_or_none()
    if ch is None:
        raise ValidationError(
            message=f"channel 不存在或已删除: {req.channel_id}"
        )

    # 唯一约束预检（COALESCE 处理 NULL）—— 走 DB UNIQUE 也能拦但提前给清晰错误
    existing = await _find_by_route_key(
        session,
        group_id=req.group_id,
        model_code=req.model_code,
        channel_id=req.channel_id,
    )
    if existing is not None:
        raise ValidationError(
            message=(
                f"重复 ability：(group_id={req.group_id}, "
                f"model_code={req.model_code}, channel_id={req.channel_id}) 已存在"
            )
        )

    a = Ability(
        group_id=req.group_id,
        model_code=req.model_code,
        channel_id=req.channel_id,
        priority=req.priority,
        weight=req.weight,
        enabled=True,
    )
    session.add(a)
    await session.flush()
    await session.refresh(a)

    provider_code = (
        await session.execute(
            select(Provider.code).where(Provider.id == ch.provider_id)
        )
    ).scalar_one_or_none()
    item = _row_to_item(a, ch, provider_code)
    await session.commit()
    return item


async def update_ability(
    session: AsyncSession, ability_id: int, req: UpdateAbilityRequest
) -> AbilityItem:
    a = await _load_ability(session, ability_id)
    if req.priority is not None:
        a.priority = req.priority
    if req.weight is not None:
        a.weight = req.weight
    if req.enabled is not None:
        a.enabled = req.enabled
    await session.flush()

    ch = (
        await session.execute(
            select(Channel).where(Channel.id == a.channel_id)
        )
    ).scalar_one_or_none()
    provider_code = None
    if ch is not None:
        provider_code = (
            await session.execute(
                select(Provider.code).where(Provider.id == ch.provider_id)
            )
        ).scalar_one_or_none()
    await session.refresh(a)
    item = _row_to_item(a, ch, provider_code)
    await session.commit()
    return item


async def delete_ability(session: AsyncSession, ability_id: int) -> None:
    """硬删 —— ability 不带软删，删了就没了；channel 软删时由 CASCADE 自动清理"""
    a = await _load_ability(session, ability_id)
    await session.execute(delete(Ability).where(Ability.id == a.id))
    await session.commit()


# ── 内部 helper ────────────────────────────────────────────


async def _load_ability(session: AsyncSession, ability_id: int) -> Ability:
    a = (
        await session.execute(
            select(Ability).where(Ability.id == ability_id)
        )
    ).scalar_one_or_none()
    if a is None:
        raise BusinessError(
            ResultCode.AgentNotFound, message=f"ability 不存在: {ability_id}"
        )
    return a


async def _find_by_route_key(
    session: AsyncSession,
    *,
    group_id: int | None,
    model_code: str,
    channel_id: int,
) -> Ability | None:
    stmt = select(Ability).where(
        Ability.model_code == model_code,
        Ability.channel_id == channel_id,
    )
    if group_id is None:
        stmt = stmt.where(Ability.group_id.is_(None))
    else:
        stmt = stmt.where(Ability.group_id == group_id)
    return (await session.execute(stmt)).scalar_one_or_none()


def _row_to_item(
    a: Ability, ch: Channel | None, provider_code: str | None
) -> AbilityItem:
    return AbilityItem(
        id=a.id,
        group_id=a.group_id,
        model_code=a.model_code,
        channel_id=a.channel_id,
        channel_name=ch.name if ch is not None else None,
        provider_code=provider_code,
        priority=a.priority,
        weight=a.weight,
        enabled=a.enabled,
        created_at=a.created_at,
        updated_at=a.updated_at,
    )
