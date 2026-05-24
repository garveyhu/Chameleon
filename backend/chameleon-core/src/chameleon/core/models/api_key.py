"""ApiKey + CallLog 模型

v0.2 重构：
- ApiKey.app_id String 删除 unique 约束（一 app 多 key），加 FK 引用 apps.app_key
- ApiKey.created_by_id 重命名为 created_by_user_id + 加 FK 引用 users.id
- CallLog.app_id / agent_key 加 FK；加 api_key_id FK + error_class 字段
"""

from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from chameleon.core.models.base import Base, TimestampMixin
from chameleon.core.utils.snowflake import next_id


class ApiKey(Base, TimestampMixin):
    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, default=next_id)
    # app_id 是字符串 slug（对外可读，业务方调用时不直接出现，但所有表统一）
    # FK 引用 apps.app_key（CASCADE：删 app 时 key 一起删）
    app_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("apps.app_key", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    scopes: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        Index("ix_api_keys_app", "app_id"),
        Index("ix_api_keys_revoked", "revoked_at"),
        Index("ix_api_keys_created_by", "created_by_user_id"),
    )


class CallLog(Base):
    __tablename__ = "call_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, default=next_id)
    request_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    app_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("apps.app_key", ondelete="CASCADE"),
        nullable=False,
    )
    # agent_key FK 推到 P5（agents 表由 registry sync 在 P5 填充）
    agent_key: Mapped[str] = mapped_column(String(64), nullable=False)
    api_key_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("api_keys.id", ondelete="SET NULL"),
        nullable=True,
    )
    session_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # P23.C1 计费多维：user / model / channel 三维（全 NULLABLE，老数据零迁移）
    # user_id：发起调用的用户（API-key 调用可能为 NULL，admin/playground 有值）
    user_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    # model_code：实际命中的模型编码（路由后），cost dashboard 按模型聚合
    model_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # channel_id：实际命中的上游 channel（failover 后），按渠道聚合 / 成本归因
    channel_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("channels.id", ondelete="SET NULL"),
        nullable=True,
    )
    stream: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    code: Mapped[int] = mapped_column(Integer, nullable=False)
    error_class: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # P22.1：成本（按当时价目算并存死；改价目不溯源）—— 原始模型成本，不含分组倍率
    cost_usd: Mapped[float | None] = mapped_column(Numeric(12, 6), nullable=True)
    # P23.C5：计费分组倍率（写入时存死）；effective cost = cost_usd × group_ratio
    group_ratio: Mapped[float | None] = mapped_column(Numeric(6, 3), nullable=True)
    # P16-E2 trace: spans [{name, start_ms, end_ms, status, error?, meta?}]
    spans: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # 入参快照（input + options + history 摘要等）
    request_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # 出参快照（answer + steps + citations + tool_calls + usage）
    response_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # P17.C1 嵌套 Observation：parent_id 指向同表父 request_id；NULL = trace root
    parent_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # observation 类型枚举（trace/span/generation/agent/tool/retriever/evaluator/embedding/guardrail）
    observation_type: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="generation", default="generation"
    )
    # 首 token 延迟（流式可用），ms
    completion_start_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_call_logs_created_at", "created_at"),
        Index("ix_call_logs_app_created", "app_id", "created_at"),
        Index("ix_call_logs_agent_created", "agent_key", "created_at"),
        Index("ix_call_logs_success_created", "success", "created_at"),
        Index("ix_call_logs_api_key", "api_key_id"),
        Index("ix_call_logs_parent", "parent_id"),
        Index("ix_call_logs_type", "observation_type"),
        # P23.C1 计费多维聚合（C8 cost dashboard group by dim 在时间窗内）
        Index("ix_call_logs_user_created", "user_id", "created_at"),
        Index("ix_call_logs_model_created", "model_code", "created_at"),
        Index("ix_call_logs_channel_created", "channel_id", "created_at"),
    )
