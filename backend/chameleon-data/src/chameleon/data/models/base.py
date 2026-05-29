"""ORM 基类 + 公共 mixin

约定：
- 全部主键 BIGINT，雪花 ID（应用层生成，default 走 utils.snowflake.next_id）
- created_at / updated_at 通过 TimestampMixin 自动
- 软删用 SoftDeleteMixin（deleted_at TIMESTAMPTZ NULL）
- 字符串枚举字段一律 VARCHAR(N) + 应用层 Enum 校验，不用 PG 原生 ENUM
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from chameleon.data.utils.snowflake import next_id


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class SoftDeleteMixin:
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


def snowflake_pk() -> Mapped[int]:
    """雪花 ID 主键 helper"""
    return mapped_column(BigInteger, primary_key=True, default=next_id)
