"""P22.5 PR #83: app_templates 表 —— 应用市场 template gallery

Revision ID: p22_w47_app_templates
Revises: p22_w45_multimodal_kb
Create Date: 2027-04-12 12:00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "p22_w47_app_templates"
down_revision: Union[str, Sequence[str], None] = "p22_w45_multimodal_kb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "app_templates",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("spec_json", sa.JSON(), nullable=False),
        sa.Column("cover_image", sa.String(length=512), nullable=True),
        sa.Column(
            "verified",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "downloads",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "created_by_user_id", sa.BigInteger(), nullable=True
        ),
        sa.Column(
            "workspace_id",
            sa.BigInteger(),
            sa.ForeignKey("workspaces.id", ondelete="SET NULL"),
            nullable=True,
        ),
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
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_app_templates_verified_cat",
        "app_templates",
        ["verified", "category"],
    )
    op.create_index(
        "ix_app_templates_downloads", "app_templates", ["downloads"]
    )


def downgrade() -> None:
    op.drop_index(
        "ix_app_templates_downloads", table_name="app_templates"
    )
    op.drop_index(
        "ix_app_templates_verified_cat", table_name="app_templates"
    )
    op.drop_table("app_templates")
