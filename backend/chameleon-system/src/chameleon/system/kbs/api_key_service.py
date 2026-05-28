"""知识库作用域 API 密钥 CRUD

scope_type='kb'、scope_ref=kb_key，前缀 kbs-。仅对该知识库的公开 API
（/v1/kb/* —— key 即 KB 身份）有效；全局密钥（scope_type=global）通吃。复用通用
api_key 服务，仅在此封装「按 KB 归属」的增列改。
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.api.exceptions import BusinessError, ResultCode
from chameleon.core.models import ApiKey, KnowledgeBase
from chameleon.system.api_key import service as api_key_service
from chameleon.system.api_key.schemas import (
    ApiKeyCreated,
    ApiKeyItem,
    CreateApiKeyRequest,
)


async def _get_kb(session: AsyncSession, kb_id: int) -> KnowledgeBase:
    kb = (
        await session.execute(
            select(KnowledgeBase).where(
                KnowledgeBase.id == kb_id, KnowledgeBase.deleted_at.is_(None)
            )
        )
    ).scalar_one_or_none()
    if kb is None:
        raise BusinessError(
            ResultCode.KnowledgeBaseNotFound, message=f"kb 不存在: {kb_id}"
        )
    return kb


async def create_kb_key(
    session: AsyncSession, kb_id: int, name: str
) -> ApiKeyCreated:
    """为该知识库生成一个 kb 作用域密钥（前缀 kbs-，仅对该 KB 公开 API 有效）。"""
    kb = await _get_kb(session, kb_id)
    req = CreateApiKeyRequest(
        app_id=f"kb-{kb.kb_key}",
        name=name or f"{kb.name} 密钥",
        scope_type="kb",
        scope_ref=kb.kb_key,
    )
    return await api_key_service.create_api_key(session, req)


async def list_kb_keys(session: AsyncSession, kb_id: int) -> list[ApiKeyItem]:
    """列该 KB 的未吊销密钥（最新在前）。"""
    kb = await _get_kb(session, kb_id)
    rows = (
        (
            await session.execute(
                select(ApiKey)
                .where(
                    ApiKey.scope_type == "kb",
                    ApiKey.scope_ref == kb.kb_key,
                    ApiKey.revoked_at.is_(None),
                )
                .order_by(ApiKey.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return [ApiKeyItem.model_validate(r) for r in rows]


async def revoke_kb_key(
    session: AsyncSession, kb_id: int, key_id: int
) -> ApiKeyItem:
    """吊销该 KB 名下的某个密钥（校验归属）。"""
    kb = await _get_kb(session, kb_id)
    row = (
        await session.execute(select(ApiKey).where(ApiKey.id == key_id))
    ).scalar_one_or_none()
    if row is None or row.scope_type != "kb" or row.scope_ref != kb.kb_key:
        raise BusinessError(ResultCode.Fail, message="密钥不存在或不属于该知识库")
    return await api_key_service.revoke_api_key(session, key_id)
