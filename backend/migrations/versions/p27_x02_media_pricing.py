"""P27: media_pricing 表（媒体生成计费：按张 / 按秒 + 分辨率分档，CNY）

Revision ID: p27_x02_media_pricing
Revises: p27_x01_drop_upstream_group
Create Date: 2026-06-07 02:30:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "p27_x02_media_pricing"
down_revision: Union[str, Sequence[str], None] = "p27_x01_drop_upstream_group"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "media_pricing",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("model_code", sa.String(length=64), nullable=False),
        sa.Column("unit", sa.String(length=32), nullable=False),
        sa.Column(
            "tier", sa.String(length=32), nullable=False, server_default=""
        ),
        sa.Column(
            "price", sa.Numeric(precision=10, scale=6), nullable=False
        ),
        sa.Column(
            "currency", sa.String(length=8), nullable=False, server_default="CNY"
        ),
        sa.Column(
            "effective_from", sa.DateTime(timezone=True), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "model_code",
            "unit",
            "tier",
            "effective_from",
            name="uq_media_pricing_code_unit_tier_ts",
        ),
    )
    op.create_index(
        "ix_media_pricing_lookup",
        "media_pricing",
        ["model_code", "unit", "tier", "effective_from"],
    )


def downgrade() -> None:
    op.drop_index("ix_media_pricing_lookup", table_name="media_pricing")
    op.drop_table("media_pricing")
