"""会话与可观测重构（S1）：drop conversations + create sessions + 加 end_user_id + embed_configs 增强

[SCHEMA-CHANGE] 大动表结构。背景见 docs/plans/2026-05-28-session-and-observability-refactor.md。

变更要点：
- conversations 整删，重设 sessions（加 end_user_id / api_key_id 等终端用户身份层）
- messages 清空（孤儿数据）+ 加 end_user_id 冗余列
- call_logs 加 end_user_id 冗余列（按用户分析免 join）
- embed_configs 加 api_key_id FK（绑 owner key，决策点 D2=是）+ session_policy JSON（嵌入式会话策略）

注意：drop 不迁数据。本地 dev 库重置；线上未上生产，无影响。

Revision ID: p25_a01_session_redesign
Revises: p24_w70_add_app_icon
Create Date: 2026-05-28 00:00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "p25_a01_session_redesign"
down_revision: Union[str, Sequence[str], None] = "p24_w70_add_app_icon"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── 1. 清孤儿 messages（rows 会随 conversations drop 失去父引用，先 TRUNCATE）─
    op.execute("TRUNCATE TABLE messages")

    # ── 2. drop conversations（含其 index）──────────────────────────────────
    op.drop_index("ix_conversations_app_last_msg", table_name="conversations")
    op.drop_index("ix_conversations_agent_last_msg", table_name="conversations")
    op.drop_table("conversations")

    # ── 3. create sessions ─────────────────────────────────────────────────
    op.create_table(
        "sessions",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("agent_key", sa.String(length=64), nullable=False),
        sa.Column("app_id", sa.String(length=64), nullable=False),
        sa.Column(
            "api_key_id",
            sa.BigInteger(),
            sa.ForeignKey("api_keys.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("end_user_id", sa.String(length=128), nullable=True),
        sa.Column("provider_conv_id", sa.String(length=255), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("session_id", name="sessions_session_id_key"),
    )
    op.create_index("ix_sessions_agent_key", "sessions", ["agent_key"])
    op.create_index("ix_sessions_app_id", "sessions", ["app_id"])
    op.create_index("ix_sessions_end_user_id", "sessions", ["end_user_id"])
    op.create_index("ix_sessions_api_key_id", "sessions", ["api_key_id"])
    op.create_index("ix_sessions_last_message_at", "sessions", ["last_message_at"])
    # 列表热查：某 app 下某 end_user 按活跃倒序
    op.create_index(
        "ix_sessions_app_user_last_msg",
        "sessions",
        ["app_id", "end_user_id", "last_message_at"],
    )

    # ── 4. messages 加 end_user_id ────────────────────────────────────────
    op.add_column(
        "messages",
        sa.Column("end_user_id", sa.String(length=128), nullable=True),
    )
    op.create_index("ix_messages_end_user_id", "messages", ["end_user_id"])

    # ── 5. call_logs 加 end_user_id ───────────────────────────────────────
    op.add_column(
        "call_logs",
        sa.Column("end_user_id", sa.String(length=128), nullable=True),
    )
    op.create_index(
        "ix_call_logs_end_user_created",
        "call_logs",
        ["end_user_id", "created_at"],
    )

    # ── 6. embed_configs 加 api_key_id FK + session_policy JSON ──────────
    op.add_column(
        "embed_configs",
        sa.Column(
            "api_key_id",
            sa.BigInteger(),
            sa.ForeignKey("api_keys.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_embed_configs_api_key", "embed_configs", ["api_key_id"])
    op.add_column(
        "embed_configs",
        sa.Column("session_policy", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    # best-effort 回滚：恢复 conversations + 移除新增列。数据已丢，结构回退。

    # ── 6. embed_configs 回退 ─────────────────────────────────────────────
    op.drop_column("embed_configs", "session_policy")
    op.drop_index("ix_embed_configs_api_key", table_name="embed_configs")
    op.drop_constraint(
        "embed_configs_api_key_id_fkey", "embed_configs", type_="foreignkey"
    )
    op.drop_column("embed_configs", "api_key_id")

    # ── 5. call_logs 回退 ────────────────────────────────────────────────
    op.drop_index("ix_call_logs_end_user_created", table_name="call_logs")
    op.drop_column("call_logs", "end_user_id")

    # ── 4. messages 回退 ─────────────────────────────────────────────────
    op.drop_index("ix_messages_end_user_id", table_name="messages")
    op.drop_column("messages", "end_user_id")

    # ── 3. drop sessions ────────────────────────────────────────────────
    op.drop_index("ix_sessions_app_user_last_msg", table_name="sessions")
    op.drop_index("ix_sessions_last_message_at", table_name="sessions")
    op.drop_index("ix_sessions_api_key_id", table_name="sessions")
    op.drop_index("ix_sessions_end_user_id", table_name="sessions")
    op.drop_index("ix_sessions_app_id", table_name="sessions")
    op.drop_index("ix_sessions_agent_key", table_name="sessions")
    op.drop_table("sessions")

    # ── 2. 重建 conversations（与 p24_w68 之后状态一致：app_id 无 FK）──
    op.create_table(
        "conversations",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("agent_key", sa.String(length=64), nullable=False),
        sa.Column("app_id", sa.String(length=64), nullable=False),
        sa.Column("provider_conv_id", sa.String(length=255), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("session_id", name="conversations_session_id_key"),
    )
    op.create_index(
        "ix_conversations_app_last_msg",
        "conversations",
        ["app_id", "last_message_at"],
    )
    op.create_index(
        "ix_conversations_agent_last_msg",
        "conversations",
        ["agent_key", "last_message_at"],
    )

    # ── 1. messages truncate 不可逆 ─────────────────────────────────────
