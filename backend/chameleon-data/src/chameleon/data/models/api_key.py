"""ApiKey + CallLog 模型

单租户重构（块2 Key 管理）：apps「应用容器」整删，归属重锚到 api_key。
- app_id 降级为自由字符串「调用方/来源标签」，去掉 FK→apps，仅留 index。
  有 key 的调用靠 api_key_id 精确反查；无 key 的 admin/playground/eval 调用
  靠 app_id 字符串标签（如 "admin"/"system"/"__eval__"）兜底。
- 配额字段 qpm_limit / qpd_limit 从被删的 App 搬到 ApiKey（仅落字段，暂不 enforce）。
- scope_type：global = 通吃所有服务；app = 仅某智能体/应用；kb = 仅某知识库。
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

from chameleon.data.models.base import Base, TimestampMixin
from chameleon.data.utils.snowflake import next_id


class ApiKey(Base, TimestampMixin):
    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, default=next_id)
    # app_id 是自由「调用方/来源标签」（无 FK，仅 index）：有 key 的调用靠 api_key_id
    # 精确反查，此标签只用于聚合/展示（如 "admin" / "system" / name 的 slug）。
    app_id: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    # 明文留存：支持生成后重复进来复制（产品取舍——便利优先于"仅一次回显"）。
    # 注意：DB 因此持有可用密钥，泄露即等同泄密；老数据为 None（只能看前缀）。
    plain_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # 作用域（key「能访问什么」，与容器无关）：global = 通吃所有服务；
    # app = 仅某工作流/智能体；kb = 仅某知识库。scope_ref 为域内目标：
    # app → agent_key；kb → kb_key；global → NULL。前缀按域区分（chm_/app-/kbs-）。
    scope_type: Mapped[str] = mapped_column(
        String(16), nullable=False, default="global", server_default="global"
    )
    scope_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    scopes: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 配额（从被删的 App 搬来，nullable；仅落字段，暂不做 enforcement）
    qpm_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    qpd_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
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
        Index("ix_api_keys_scope", "scope_type", "scope_ref"),
    )


class CallLog(Base):
    __tablename__ = "call_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, default=next_id)
    request_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    # app_id 自由「调用方/来源标签」（无 FK，仅 index）—— 同 ApiKey.app_id 语义
    app_id: Mapped[str] = mapped_column(String(64), nullable=False)
    # agent_key FK 推到 P5（agents 表由 registry sync 在 P5 填充）
    agent_key: Mapped[str] = mapped_column(String(64), nullable=False)
    api_key_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("api_keys.id", ondelete="SET NULL"),
        nullable=True,
    )
    session_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # P23.C1 计费多维：user / model / channel 三维（全 NULLABLE，老数据零迁移）
    # user_id：后台操作者（admin / playground）；与 end_user_id（终端用户）区分
    user_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    # S5 重构：终端用户外部 id（接入方维护；冗余落库以免按用户聚合时回去 join sessions）
    end_user_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # model_code：实际命中的模型编码，cost dashboard 按模型聚合
    model_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # channel：调用来源渠道（api/openai/embed/playground/internal），入口处盖章；
    # 会话账本按渠道筛选/溯源。NULL = 未标注（如图内部子观测）。
    channel: Mapped[str | None] = mapped_column(String(16), nullable=True)
    stream: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    code: Mapped[int] = mapped_column(Integer, nullable=False)
    error_class: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # P22.1：成本（按当时价目算并存死；改价目不溯源）—— 原始模型成本
    cost_usd: Mapped[float | None] = mapped_column(Numeric(12, 6), nullable=True)
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
        Index("ix_call_logs_channel_created", "channel", "created_at"),
    )
