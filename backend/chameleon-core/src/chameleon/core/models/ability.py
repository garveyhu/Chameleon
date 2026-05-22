"""Ability ORM —— 矩阵路由表

一条 ability = "在某 group 下，调 model_code 时能路由到 channel"。
联合唯一键 (COALESCE(group_id,-1), model_code, channel_id) 保证同一
(group × model × channel) 只出现一次。

设计动机（P17.A1.2）：
原 agent 直绑 provider，无法表达"gpt-4 路由到 openai/azure/anthropic 三家"
这种多渠道场景。引入 abilities 矩阵后：
- agent → model_code（声明需要什么能力）
- model_code + (group_id?) → router → channel（运行时按 priority+weight 选）

priority/weight 算法：
- 同 model_code + 同 group 内，先取最高 priority
- 同 priority 多 channel，按 weight 加权随机（weight=0 视为等权）
- enabled=False 的整条略过

group_id 语义：
- NULL = 全局 ability，所有用户都能用
- 非 NULL = 仅指定 group 用户能路由到（P18 多租户启用）
"""

from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from chameleon.core.models.base import Base, snowflake_pk


class Ability(Base):
    """(group × model × channel) 路由矩阵单条"""

    __tablename__ = "abilities"

    id: Mapped[int] = snowflake_pk()
    # NULL = 全局；非 NULL = 指定 group 才生效
    group_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    # 调用方按 model_code 路由（如 "gpt-4", "claude-3-opus", "qwen-plus"）
    model_code: Mapped[str] = mapped_column(String(64), nullable=False)
    channel_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("channels.id", ondelete="CASCADE"),
        nullable=False,
    )
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    weight: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )

    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[object] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        # 联合唯一（NULL 用 COALESCE 折成 -1 占位）
        Index(
            "uq_abilities_route",
            text("COALESCE(group_id, -1)"),
            "model_code",
            "channel_id",
            unique=True,
        ),
        # 路由查询专用索引（覆盖最常见路径：按 model_code + enabled 过滤后按 priority 排）
        Index(
            "ix_abilities_lookup",
            "model_code",
            "enabled",
            "priority",
            "group_id",
        ),
    )
