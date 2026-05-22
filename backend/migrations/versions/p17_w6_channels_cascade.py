"""P17.C1 patch: channels.provider_id FK ON DELETE RESTRICT → CASCADE

P17.A1.1 给 channels.provider_id 设的 RESTRICT 太严，导致
seed import / provider 软删工具链都被卡。语义上 channel 不能脱离 provider
存活，CASCADE 更合理：delete provider → 其 channels 一并清理。

Revision ID: p17_w6_channels_cascade
Revises: p17_w6_observation
Create Date: 2026-05-23 13:30:00
"""

from typing import Sequence, Union

from alembic import op

revision: str = "p17_w6_channels_cascade"
down_revision: Union[str, Sequence[str], None] = "p17_w6_observation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("channels_provider_id_fkey", "channels", type_="foreignkey")
    op.create_foreign_key(
        "channels_provider_id_fkey",
        "channels",
        "providers",
        ["provider_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint("channels_provider_id_fkey", "channels", type_="foreignkey")
    op.create_foreign_key(
        "channels_provider_id_fkey",
        "channels",
        "providers",
        ["provider_id"],
        ["id"],
        ondelete="RESTRICT",
    )
