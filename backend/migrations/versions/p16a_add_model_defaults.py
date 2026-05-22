"""P16-A: add model_defaults table

Revision ID: p16a_model_defaults
Revises: a6b46fee90c0
Create Date: 2026-05-22 16:00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "p16a_model_defaults"
down_revision: Union[str, Sequence[str], None] = "a6b46fee90c0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "model_defaults",
        sa.Column("case_name", sa.String(length=32), primary_key=True),
        sa.Column(
            "model_id",
            sa.BigInteger(),
            sa.ForeignKey("models.id", ondelete="SET NULL"),
            nullable=True,
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


def downgrade() -> None:
    op.drop_table("model_defaults")
