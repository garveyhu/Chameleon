"""P17.A1.2: 新增 abilities 矩阵表 + backfill (model, default_channel) 对

abilities 表是路由的真正引擎：调用方按 model_code 路由，router 查这张表
拿到候选 channel 列表，按 priority + weight 加权选出最终 channel。

Backfill：每个 (model, model.provider 派生的 default channel) 对生成一条
NULL group_id 的全局 ability（priority=0, weight=0, enabled=随 model）。
这让 v0.3 升级用户开箱即用：不需要手工配 ability，老流程照跑。

ID 生成：用 epoch_ms*1000 + row_number 占大整数空间，避免与未来 snowflake
冲突（snowflake 实际值是 timestamp_ms << 22 量级，远大于这里）。

Revision ID: p17_w4_abilities
Revises: p17_w3_channels
Create Date: 2026-05-23 22:00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "p17_w4_abilities"
down_revision: Union[str, Sequence[str], None] = "p17_w3_channels"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
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
        sa.Column(
            "enabled", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
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
    # 联合唯一：NULL group_id 用 COALESCE 折成 -1 占位
    op.execute(
        "CREATE UNIQUE INDEX uq_abilities_route "
        "ON abilities (COALESCE(group_id, -1), model_code, channel_id)"
    )
    op.create_index(
        "ix_abilities_lookup",
        "abilities",
        ["model_code", "enabled", "priority", "group_id"],
    )

    # Backfill：每个 (model, model.provider 派生的 default channel) → 一条全局 ability
    # channel.id 是 -provider.id（见 p17_w3_channels backfill）
    op.execute(
        """
        INSERT INTO abilities (
            id, group_id, model_code, channel_id, priority, weight, enabled, created_at, updated_at
        )
        SELECT
            (EXTRACT(EPOCH FROM clock_timestamp()) * 1000000)::bigint
                + row_number() OVER (ORDER BY m.id),
            NULL,
            m.code,
            -m.provider_id::bigint,
            0,
            0,
            m.enabled,
            NOW(),
            NOW()
        FROM models m
        JOIN providers p ON m.provider_id = p.id
        JOIN channels c ON c.id = -m.provider_id::bigint
        WHERE m.deleted_at IS NULL
          AND p.deleted_at IS NULL
          AND c.deleted_at IS NULL
        ON CONFLICT DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_index("ix_abilities_lookup", table_name="abilities")
    op.execute("DROP INDEX IF EXISTS uq_abilities_route")
    op.drop_table("abilities")
