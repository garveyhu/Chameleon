"""KB collections admin service —— P20.3 PR #53

业务：admin 在 KB 下管理 collection（chunker 类型 + 索引拓扑）。

红线（plan §2 P20）：
- ⛔ collection_type 一经写入不可改 —— update 路径拒绝改 type；改 = 新建
- ⛔ 删除 collection 时关联 chunks.collection_id 置 NULL（ondelete=SET NULL）；
  不级联删 chunks（保留兼容路径的检索能力）
"""

from __future__ import annotations

from typing import Literal

from loguru import logger
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.api.exceptions import BusinessError, ResultCode
from chameleon.core.models import KbCollection, KnowledgeBase
from chameleon.core.models.kb_collection import COLLECTION_TYPES, DEFAULT_INDEXES

CollectionType = Literal["generic", "faq", "wiki", "api"]


# ── DTO ─────────────────────────────────────────────────


class CollectionItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kb_id: int
    collection_type: str
    name: str
    indexes: list[dict]
    config: dict | None = None


class CreateCollectionRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    collection_type: CollectionType = "generic"
    indexes: list[dict] | None = None  # 默认 [{name:'chunk', dim:1536, enabled:True}]
    config: dict | None = None


class UpdateCollectionRequest(BaseModel):
    """只能改 name / indexes / config；collection_type 不可改"""

    name: str | None = Field(default=None, max_length=64)
    indexes: list[dict] | None = None
    config: dict | None = None


# ── service ─────────────────────────────────────────────


async def list_collections(
    session: AsyncSession, kb_id: int
) -> list[CollectionItem]:
    rows = (
        (
            await session.execute(
                select(KbCollection)
                .where(KbCollection.kb_id == kb_id)
                .order_by(KbCollection.created_at.asc())
            )
        )
        .scalars()
        .all()
    )
    return [CollectionItem.model_validate(r) for r in rows]


async def create_collection(
    session: AsyncSession, kb_id: int, req: CreateCollectionRequest
) -> CollectionItem:
    await _assert_kb_exists(session, kb_id)
    if req.collection_type not in COLLECTION_TYPES:
        raise BusinessError(
            ResultCode.ValidationError,
            message=f"非法 collection_type={req.collection_type}",
        )
    # 同 KB 内 name 唯一
    exists = (
        await session.execute(
            select(KbCollection).where(
                KbCollection.kb_id == kb_id, KbCollection.name == req.name
            )
        )
    ).scalar_one_or_none()
    if exists is not None:
        raise BusinessError(
            ResultCode.Fail,
            message=f"KB {kb_id} 已有同名 collection: {req.name}",
        )

    row = KbCollection(
        kb_id=kb_id,
        collection_type=req.collection_type,
        name=req.name,
        indexes=list(req.indexes or DEFAULT_INDEXES),
        config=req.config,
    )
    session.add(row)
    await session.flush()
    await session.refresh(row)
    item = CollectionItem.model_validate(row)
    await session.commit()
    logger.info(
        "kb_collection created | kb={} | id={} | type={}",
        kb_id,
        row.id,
        row.collection_type,
    )
    return item


async def update_collection(
    session: AsyncSession,
    kb_id: int,
    collection_id: int,
    req: UpdateCollectionRequest,
) -> CollectionItem:
    row = await _load(session, kb_id, collection_id)
    if req.name is not None:
        row.name = req.name
    if req.indexes is not None:
        row.indexes = list(req.indexes)
    if req.config is not None:
        row.config = req.config
    await session.flush()
    await session.refresh(row)
    item = CollectionItem.model_validate(row)
    await session.commit()
    return item


async def delete_collection(
    session: AsyncSession, kb_id: int, collection_id: int
) -> None:
    await _load(session, kb_id, collection_id)  # 校验存在
    # chunks.collection_id 走 ondelete=SET NULL，留 chunks 用，但不挂在该 collection
    await session.execute(
        delete(KbCollection).where(KbCollection.id == collection_id)
    )
    await session.commit()


async def get_or_create_default(
    session: AsyncSession, kb_id: int
) -> KbCollection:
    """新建 KB 后兜底：保证至少有一个 generic 默认 collection"""
    row = (
        await session.execute(
            select(KbCollection)
            .where(KbCollection.kb_id == kb_id)
            .order_by(KbCollection.created_at.asc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if row is not None:
        return row
    new_row = KbCollection(
        kb_id=kb_id,
        collection_type="generic",
        name="default",
        indexes=list(DEFAULT_INDEXES),
        config={},
    )
    session.add(new_row)
    await session.flush()
    await session.refresh(new_row)
    return new_row


# ── helpers ─────────────────────────────────────────────


async def _assert_kb_exists(session: AsyncSession, kb_id: int) -> None:
    row = (
        await session.execute(
            select(KnowledgeBase.id).where(KnowledgeBase.id == kb_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise BusinessError(
            ResultCode.KnowledgeBaseNotFound,
            message=f"KB 不存在: {kb_id}",
        )


async def _load(
    session: AsyncSession, kb_id: int, collection_id: int
) -> KbCollection:
    row = (
        await session.execute(
            select(KbCollection).where(
                KbCollection.id == collection_id,
                KbCollection.kb_id == kb_id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise BusinessError(
            ResultCode.NotFound,
            message=f"collection 不存在: kb={kb_id} id={collection_id}",
        )
    return row
