"""P20.2: plugin_registries 表（远端 marketplace 配置）

业务：admin 配置可信的 plugin registry（marketplace URL + publishers 公钥 pinning）。
启动时拉 index.json，install 时按 publisher pinning 验签。

Revision ID: p20_w27_plugin_registries
Revises: p19_w23_message_blocks
Create Date: 2026-11-22 12:00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "p20_w27_plugin_registries"
down_revision: Union[str, Sequence[str], None] = "p19_w23_message_blocks"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "plugin_registries",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "registry_url",
            sa.String(length=256),
            nullable=False,
            unique=True,
        ),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("pubkey_pinning", sa.JSON(), nullable=True),
        sa.Column(
            "enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "last_synced_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column("cached_entries", sa.JSON(), nullable=True),
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
    )


def downgrade() -> None:
    op.drop_table("plugin_registries")
