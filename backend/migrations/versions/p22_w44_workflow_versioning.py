"""P22.3 PR #78: graphs 加 published_spec / published_version / published_at

Revision ID: p22_w44_workflow_versioning
Revises: p22_w41_audit_cost
Create Date: 2027-03-22 12:00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "p22_w44_workflow_versioning"
down_revision: Union[str, Sequence[str], None] = "p22_w41_audit_cost"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "graphs", sa.Column("published_spec", sa.JSON(), nullable=True)
    )
    op.add_column(
        "graphs",
        sa.Column(
            "published_version",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "graphs",
        sa.Column(
            "published_at", sa.DateTime(timezone=True), nullable=True
        ),
    )


def downgrade() -> None:
    op.drop_column("graphs", "published_at")
    op.drop_column("graphs", "published_version")
    op.drop_column("graphs", "published_spec")
