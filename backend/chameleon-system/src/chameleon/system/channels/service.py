"""channels 业务 service —— CRUD + 健康字段 reset

API 层只做参数校验和响应包装；本模块写 SQL / 加密 / 转换 DTO。
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.api.exceptions import (
    BusinessError,
    ResultCode,
    ValidationError,
)
from chameleon.core.models import Channel, ChannelStatus, Provider
from chameleon.core.utils.crypto import encrypt
from chameleon.system.channels.schemas import (
    ChannelHealthItem,
    ChannelItem,
    CreateChannelRequest,
    UpdateChannelRequest,
)

_VALID_STATUSES = {s.value for s in ChannelStatus}


# ── 查询 ──────────────────────────────────────────────────


async def list_channels(
    session: AsyncSession,
    *,
    provider_id: int | None = None,
    status: str | None = None,
) -> list[ChannelItem]:
    """列出 channels（含 provider.code 一并展示），按 priority desc / id 升序"""
    stmt = (
        select(Channel, Provider.code)
        .join(Provider, Channel.provider_id == Provider.id)
        .where(Channel.deleted_at.is_(None))
        .order_by(Channel.priority.desc(), Channel.id.asc())
    )
    if provider_id is not None:
        stmt = stmt.where(Channel.provider_id == provider_id)
    if status is not None:
        stmt = stmt.where(Channel.status == status)
    rows = (await session.execute(stmt)).all()
    return [_row_to_item(ch, provider_code) for ch, provider_code in rows]


async def get_channel(session: AsyncSession, channel_id: int) -> ChannelItem:
    row = (
        await session.execute(
            select(Channel, Provider.code)
            .join(Provider, Channel.provider_id == Provider.id)
            .where(Channel.id == channel_id, Channel.deleted_at.is_(None))
        )
    ).first()
    if row is None:
        raise BusinessError(
            ResultCode.AgentNotFound, message=f"channel 不存在: {channel_id}"
        )
    ch, provider_code = row
    return _row_to_item(ch, provider_code)


async def get_health(session: AsyncSession, channel_id: int) -> ChannelHealthItem:
    """实时健康快照 —— 从 channel 行直接读（failover wrapper 写入的 EWMA 字段）"""
    ch = await _load_channel(session, channel_id)
    return ChannelHealthItem(
        channel_id=ch.id,
        status=ch.status,
        fail_count=ch.fail_count,
        response_time_ms=ch.response_time_ms,
        last_failed_at=ch.last_failed_at,
        last_success_at=ch.last_success_at,
        used_quota=ch.used_quota,
    )


# ── 写 ────────────────────────────────────────────────────


async def create_channel(
    session: AsyncSession, req: CreateChannelRequest
) -> ChannelItem:
    provider = await _load_active_provider(session, req.provider_id)

    ch = Channel(
        provider_id=provider.id,
        name=req.name,
        api_key_encrypted=encrypt(req.api_key) if req.api_key else None,
        base_url=req.base_url,
        status=ChannelStatus.ENABLED.value,
        weight=req.weight,
        priority=req.priority,
    )
    session.add(ch)
    await session.flush()
    await session.refresh(ch)
    item = _row_to_item(ch, provider.code)
    await session.commit()
    return item


async def update_channel(
    session: AsyncSession, channel_id: int, req: UpdateChannelRequest
) -> ChannelItem:
    ch = await _load_channel(session, channel_id)

    if req.name is not None:
        ch.name = req.name
    if req.api_key is not None:
        # 空字符串 → 清空；非空 → 加密落盘
        ch.api_key_encrypted = encrypt(req.api_key) if req.api_key else None
    if req.base_url is not None:
        ch.base_url = req.base_url or None
    if req.status is not None:
        if req.status not in _VALID_STATUSES:
            raise ValidationError(
                message=f"status 非法: {req.status}; 取值 {sorted(_VALID_STATUSES)}"
            )
        # 手动从 auto_disabled 切回 enabled 时重置 fail_count（视为人工恢复）
        if (
            ch.status == ChannelStatus.AUTO_DISABLED.value
            and req.status == ChannelStatus.ENABLED.value
        ):
            ch.fail_count = 0
        ch.status = req.status
    if req.weight is not None:
        ch.weight = req.weight
    if req.priority is not None:
        ch.priority = req.priority

    await session.flush()
    # 在 commit 前一次取齐所有需要的字段（commit 会 expire ORM 属性）
    provider_code = (
        await session.execute(
            select(Provider.code).where(Provider.id == ch.provider_id)
        )
    ).scalar_one_or_none()
    await session.refresh(ch)
    item = _row_to_item(ch, provider_code)
    await session.commit()
    return item


async def delete_channel(session: AsyncSession, channel_id: int) -> None:
    """软删 —— 防止误操作影响审计 / 路由历史"""
    ch = await _load_channel(session, channel_id)
    ch.deleted_at = datetime.now(timezone.utc)
    # name 加 deleted 前缀避免后续同 provider 重复 name 冲突（虽未加唯一约束，
    # 业务期望 provider 内 name 唯一）
    ch.name = f"__deleted_{ch.id}_{ch.name}"
    await session.flush()
    await session.commit()


# ── 内部 helper ────────────────────────────────────────────


async def _load_active_provider(
    session: AsyncSession, provider_id: int
) -> Provider:
    p = (
        await session.execute(
            select(Provider).where(
                Provider.id == provider_id, Provider.deleted_at.is_(None)
            )
        )
    ).scalar_one_or_none()
    if p is None:
        raise ValidationError(message=f"provider 不存在或已删除: {provider_id}")
    return p


async def _load_channel(session: AsyncSession, channel_id: int) -> Channel:
    ch = (
        await session.execute(
            select(Channel).where(
                Channel.id == channel_id, Channel.deleted_at.is_(None)
            )
        )
    ).scalar_one_or_none()
    if ch is None:
        raise BusinessError(
            ResultCode.AgentNotFound, message=f"channel 不存在: {channel_id}"
        )
    return ch


def _row_to_item(ch: Channel, provider_code: str | None) -> ChannelItem:
    return ChannelItem(
        id=ch.id,
        provider_id=ch.provider_id,
        provider_code=provider_code,
        name=ch.name,
        has_api_key=bool(ch.api_key_encrypted),
        base_url=ch.base_url,
        status=ch.status,
        weight=ch.weight,
        priority=ch.priority,
        response_time_ms=ch.response_time_ms,
        fail_count=ch.fail_count,
        used_quota=ch.used_quota,
        last_failed_at=ch.last_failed_at,
        last_success_at=ch.last_success_at,
        created_at=ch.created_at,
        updated_at=ch.updated_at,
    )
