"""Agent ORM（含本地启用态 + 外部 yaml-style 注册）

source 区分来源：
- 'local'   ：本地 BaseAgent 子类，namespace 扫描入表；只能 enable/disable + 改默认参数
- 'dify'    ：DIFY 平台 chatflow / workflow / agent
- 'fastgpt' ：FastGPT 应用
- 'graph'   ：本平台可视化编排的工作流（graph_id 关联 graphs；运行时服务 published_spec）
- 其他      ：未来新平台

config provider-specific（dify 要 app_id / api_key_env，local 要 module / class）。
"""

from __future__ import annotations

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from chameleon.core.models.base import Base, SoftDeleteMixin, TimestampMixin
from chameleon.core.utils.snowflake import next_id


class Agent(Base, TimestampMixin, SoftDeleteMixin):
    """智能体注册表

    本地 agent：source='local'，provider_id NULL，local_class_path 必填。
    外部 agent：source='dify'/'fastgpt'，provider_id 关联 providers 表，config 含 app_id 等。
    """

    __tablename__ = "agents"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, default=next_id)
    # agent_key 完整 unique 让其他表的 agent_key FK 引用；软删时更名释放
    agent_key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("providers.id", ondelete="SET NULL"), nullable=True
    )
    local_class_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # source='graph' 时关联编排的工作流；运行时服务其 published_spec
    graph_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("graphs.id", ondelete="SET NULL"), nullable=True
    )
    config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # agentkit 多具名模型槽绑定：{槽名: 已配置模型 code}，如 {"chat": "qwen-plus"}。
    # 仅 source='local' 的 @agent 智能体使用；web "关联模型" tab 写入，运行时 ctx.llm(slot) 读。
    model_bindings: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # 默认模型用 code（"qwen-plus" 这种品牌名 key）而非 FK id：跨环境稳定 /
    # 跟 model_bindings JSON 内的 key 风格一致 / 避免 trace 路径多查一跳 model 表
    default_model_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tags: Mapped[list | None] = mapped_column(JSON, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # 头像：用户上传图片缩放后的 data URL（None 用默认按类型图标）
    icon: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_agents_source", "source"),
        Index("ix_agents_enabled", "enabled"),
    )
