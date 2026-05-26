"""KB 元数据字段 admin service —— KB-P5

业务：admin 在 KB 下定义元数据字段（key/label/类型/选项）。文档值存 Document.meta，
检索按字段值过滤召回（见 retrieval metadata_filters）。
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.core.api.exceptions import BusinessError, ResultCode
from chameleon.core.models import KbMetadataField, KnowledgeBase
from chameleon.core.models.kb_metadata_field import METADATA_FIELD_TYPES

FieldType = Literal["string", "number", "select", "time"]
_KEY_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]*$")


class MetadataFieldItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kb_id: int
    key: str
    label: str
    field_type: str
    options: list | None = None


class CreateMetadataFieldRequest(BaseModel):
    key: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=128)
    field_type: FieldType = "string"
    options: list[str] | None = None


async def _assert_kb_exists(session: AsyncSession, kb_id: int) -> None:
    kb = (
        await session.execute(
            select(KnowledgeBase).where(KnowledgeBase.id == kb_id)
        )
    ).scalar_one_or_none()
    if kb is None:
        raise BusinessError(ResultCode.Fail, message=f"知识库不存在: {kb_id}")


async def list_fields(
    session: AsyncSession, kb_id: int
) -> list[MetadataFieldItem]:
    rows = (
        (
            await session.execute(
                select(KbMetadataField)
                .where(KbMetadataField.kb_id == kb_id)
                .order_by(KbMetadataField.created_at.asc())
            )
        )
        .scalars()
        .all()
    )
    return [MetadataFieldItem.model_validate(r) for r in rows]


async def create_field(
    session: AsyncSession, kb_id: int, req: CreateMetadataFieldRequest
) -> MetadataFieldItem:
    await _assert_kb_exists(session, kb_id)
    if req.field_type not in METADATA_FIELD_TYPES:
        raise BusinessError(
            ResultCode.ValidationError, message=f"非法 field_type={req.field_type}"
        )
    if not _KEY_RE.match(req.key):
        raise BusinessError(
            ResultCode.ValidationError,
            message="key 须以字母开头，仅含字母/数字/下划线",
        )
    if req.field_type == "select" and not req.options:
        raise BusinessError(
            ResultCode.ValidationError, message="select 类型必须提供 options"
        )
    exists = (
        await session.execute(
            select(KbMetadataField).where(
                KbMetadataField.kb_id == kb_id, KbMetadataField.key == req.key
            )
        )
    ).scalar_one_or_none()
    if exists is not None:
        raise BusinessError(
            ResultCode.Fail, message=f"KB {kb_id} 已有同 key 字段: {req.key}"
        )
    row = KbMetadataField(
        kb_id=kb_id,
        key=req.key,
        label=req.label,
        field_type=req.field_type,
        options=req.options if req.field_type == "select" else None,
    )
    session.add(row)
    await session.flush()
    await session.refresh(row)
    return MetadataFieldItem.model_validate(row)


async def delete_field(session: AsyncSession, kb_id: int, field_id: int) -> None:
    result = await session.execute(
        delete(KbMetadataField).where(
            KbMetadataField.id == field_id, KbMetadataField.kb_id == kb_id
        )
    )
    if not result.rowcount:
        raise BusinessError(ResultCode.Fail, message=f"字段不存在: {field_id}")
    await session.flush()
