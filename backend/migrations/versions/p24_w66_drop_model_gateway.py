"""块4: 移除内部模型网关（Channels + Abilities）

[SCHEMA-CHANGE] 删除内部模型网关层：channels / abilities 两表 +
call_logs.channel_id + agents.preferred_model_code。凭证回归 provider 直连
（如把 oneapi 之类网关作为一个 provider 接入），不再做跨上游 LB / failover。

删表前先把每个 provider 的主 channel 的 key/base_url 回灌到 provider
（仅当 provider 自身为空），保住 p17 backfill 之后只在 channel 上做过的编辑。

Revision ID: p24_w66_drop_model_gateway
Revises: p23_w65_api_key_scope
Create Date: 2026-05-27 17:15:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "p24_w66_drop_model_gateway"
down_revision: Union[str, Sequence[str], None] = "p23_w65_api_key_scope"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. 删表前回灌凭证：provider 为空则取其主 channel 的 key/base_url
    #    主 channel = 该 provider 下未删除、优先 enabled、priority 最高、id 最大的一条
    op.execute(
        """
        UPDATE providers p SET
            api_key_encrypted = COALESCE(NULLIF(p.api_key_encrypted, ''), c.api_key_encrypted),
            base_url = COALESCE(NULLIF(p.base_url, ''), c.base_url)
        FROM (
            SELECT DISTINCT ON (provider_id)
                provider_id,
                COALESCE(api_key_encrypted, keys->>0) AS api_key_encrypted,
                base_url
            FROM channels
            WHERE deleted_at IS NULL
            ORDER BY provider_id, (status = 'enabled') DESC, priority DESC, id DESC
        ) c
        WHERE p.id = c.provider_id
        """
    )

    # 2. call_logs.channel_id（FK→channels）：先删索引再删列（PG 删列连带 FK）
    op.drop_index("ix_call_logs_channel_created", table_name="call_logs")
    op.drop_column("call_logs", "channel_id")

    # 3. abilities（FK→channels CASCADE）先删，再删 channels
    op.drop_table("abilities")
    op.drop_table("channels")

    # 4. agents.preferred_model_code（仅网关矩阵路由用过）
    op.drop_column("agents", "preferred_model_code")


def downgrade() -> None:
    # best-effort：重建结构（不恢复数据）
    op.add_column(
        "agents",
        sa.Column("preferred_model_code", sa.String(length=64), nullable=True),
    )

    op.create_table(
        "channels",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "provider_id",
            sa.BigInteger(),
            sa.ForeignKey("providers.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("api_key_encrypted", sa.Text(), nullable=True),
        sa.Column("keys", sa.JSON(), nullable=True),
        sa.Column("base_url", sa.String(length=512), nullable=True),
        sa.Column(
            "status", sa.String(length=16), nullable=False, server_default="enabled"
        ),
        sa.Column("weight", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("response_time_ms", sa.Integer(), nullable=True),
        sa.Column("fail_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("used_quota", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("last_failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_channels_provider", "channels", ["provider_id"])
    op.create_index(
        "ix_channels_status_priority",
        "channels",
        ["status", "priority"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    op.create_table(
        "abilities",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("group_id", sa.BigInteger(), nullable=True),
        sa.Column("model_code", sa.String(length=64), nullable=False),
        sa.Column(
            "channel_id",
            sa.BigInteger(),
            sa.ForeignKey("channels.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("weight", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_abilities_route "
        "ON abilities (COALESCE(group_id, -1), model_code, channel_id)"
    )
    op.create_index(
        "ix_abilities_lookup",
        "abilities",
        ["model_code", "enabled", "priority", "group_id"],
    )

    op.add_column(
        "call_logs",
        sa.Column(
            "channel_id",
            sa.BigInteger(),
            sa.ForeignKey("channels.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_call_logs_channel_created", "call_logs", ["channel_id", "created_at"]
    )
