"""KbMetadataField ORM —— KB-P5 元数据字段体系

KB（dataset）级字段定义：一个 KB 可定义 N 个元数据字段（key/label/类型/选项），
每个文档在 Document.meta 里按 key 存值；检索可按字段值过滤召回。

field_type：
- string  自由文本
- number  数值
- select  枚举（options 为候选值列表）
- time    日期 / 时间（ISO 字符串）
"""

from __future__ import annotations

from sqlalchemy import (
    JSON,
    BigInteger,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from chameleon.data.models.base import Base, TimestampMixin, snowflake_pk

METADATA_FIELD_TYPES = ("string", "number", "select", "time")


class KbMetadataField(Base, TimestampMixin):
    """KB 下的一个元数据字段定义"""

    __tablename__ = "kb_metadata_fields"

    id: Mapped[int] = snowflake_pk()
    kb_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
        nullable=False,
    )
    # 写入 Document.meta 用的 key（KB 下唯一）
    key: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str] = mapped_column(String(128), nullable=False)
    # string / number / select / time
    field_type: Mapped[str] = mapped_column(
        String(16), nullable=False, default="string"
    )
    # select 类型的候选值列表；其它类型为 None
    options: Mapped[list | None] = mapped_column(JSON, nullable=True)

    __table_args__ = (
        UniqueConstraint("kb_id", "key", name="uq_kb_metadata_fields_kb_key"),
        Index("ix_kb_metadata_fields_kb", "kb_id"),
    )
