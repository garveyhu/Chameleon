"""P17.A1.1: 新增 channels 表 + backfill provider.api_key → 默认 channel

新表 channels：一个 provider 可有多 channel（多 key 池 / failover / 路由优先级），
为 P17.A1.2 abilities 矩阵 + P17.A2 failover 铺路。

Backfill 策略：
- 每个 deleted_at IS NULL 的 provider 派生 1 个 name='default' 的 channel
- channel.api_key_encrypted 拷贝自 provider.api_key_encrypted（密文直接复制，主密钥相同）
- channel.base_url 拷贝自 provider.base_url（运行时优先取 channel 覆盖）
- status 沿用 provider.enabled
- channel.id 用 snowflake (默认 NEXTVAL 风格)；用 SQL 表达式生成避免 Python 侧 ID

兼容期：provider.api_key_encrypted 保留不删，P17 W4 abilities 路由替换完
全切到 channel 后再 deprecate。

Revision ID: p17_w3_channels
Revises: p16e2_spans
Create Date: 2026-05-23 18:00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "p17_w3_channels"
down_revision: Union[str, Sequence[str], None] = "p16e2_spans"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. 建表
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
        sa.Column("base_url", sa.String(length=512), nullable=True),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default="enabled",
        ),
        sa.Column("weight", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("response_time_ms", sa.Integer(), nullable=True),
        sa.Column("fail_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "used_quota", sa.BigInteger(), nullable=False, server_default="0"
        ),
        sa.Column(
            "last_failed_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column(
            "last_success_at", sa.DateTime(timezone=True), nullable=True
        ),
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

    # 2. Backfill：每个 provider 派生 1 个 default channel
    #
    # 用 PG 的 statement_timestamp() + sequence 风格生成 id 复杂；
    # 实际上 backfill 在 Python 侧生成更可控 —— 直接用 PG 的 random + epoch ms
    # 拼一个安全的 bigint（不冲突 snowflake，避免 ID 重叠）。
    # 这里走"PG 临时表 + generate_series"的简易路径：
    #   id = - (provider.id)   占负数空间，确保不与未来 snowflake 冲突
    op.execute(
        """
        INSERT INTO channels (
            id, provider_id, name, api_key_encrypted, base_url, status,
            weight, priority, fail_count, used_quota, created_at, updated_at
        )
        SELECT
            -p.id::bigint,
            p.id,
            'default',
            p.api_key_encrypted,
            p.base_url,
            CASE WHEN p.enabled THEN 'enabled' ELSE 'manual_disabled' END,
            0, 0, 0, 0,
            p.created_at,
            NOW()
        FROM providers p
        WHERE p.deleted_at IS NULL
        ON CONFLICT (id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_index("ix_channels_status_priority", table_name="channels")
    op.drop_index("ix_channels_provider", table_name="channels")
    op.drop_table("channels")
