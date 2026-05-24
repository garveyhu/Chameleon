"""Channel ORM —— 一个 channel = 一个 provider 的一条上游 key

设计动机（P17.A1）：
原 provider 表把"配置 + key + 状态"都塞在一起，无法实现：
- 同一个上游（如 OpenAI）多 key 池
- 单个 channel 自动失败 disable 不影响 provider 整体
- 一模型多 channel 智能路由（P17.A1.2 abilities 矩阵的前置）

新模型：providers 退化为"分类 + 默认 base_url"，运行时凭证全部走 channels。
provider.api_key_encrypted 兼容期保留（P17 W4 后弃用）。
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from chameleon.core.models.base import (
    Base,
    SoftDeleteMixin,
    TimestampMixin,
    snowflake_pk,
)
from chameleon.core.models.workspace import WorkspaceScopedMixin


class ChannelStatus(StrEnum):
    """channel 生命周期状态"""

    ENABLED = "enabled"  # 正常可路由
    AUTO_DISABLED = "auto_disabled"  # 连续失败被监控自动停用，可重新启用
    MANUAL_DISABLED = "manual_disabled"  # 管理员手动停用


class Channel(Base, TimestampMixin, SoftDeleteMixin, WorkspaceScopedMixin):
    """provider 凭证 + 调度元数据

    跟 provider 是多对一：一个 provider 可对应 N 个 channel（不同 key / 不同
    base_url 覆盖 / 不同优先级）。
    """

    __tablename__ = "channels"

    id: Mapped[int] = snowflake_pk()
    provider_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("providers.id", ondelete="CASCADE"),
        nullable=False,
    )
    # 同一 provider 下唯一名（便于 admin 区分多 key），不强制全局唯一
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    # AES-GCM 加密（同 provider.api_key_encrypted 主密钥）—— 单 key 模式
    api_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    # P23.C7 多 key 池：加密 key 字符串列表；非空时走 key_pool 轮转，空则回退单 key
    keys: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # 可选覆盖 provider.base_url（不同代理 / 不同区域）
    base_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # 生命周期 —— 字符串而非 PG enum（base.py 约定）
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=ChannelStatus.ENABLED.value
    )
    # 调度参数
    weight: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # 健康监控字段（P17.A2 写入；CRUD 只展示）
    response_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fail_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    used_quota: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    last_failed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_success_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        Index("ix_channels_provider", "provider_id"),
        Index(
            "ix_channels_status_priority",
            "status",
            "priority",
            postgresql_where="deleted_at IS NULL",
        ),
    )
