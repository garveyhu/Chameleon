"""P21.3 PR #65: kb_consistency_reports + chunks.quarantined / quarantine_reason

业务：KB 一致性扫描结果落表；chunks 加半软删标记。
红线（plan §2 P21）：scan 只标 quarantined=True，不物理删；repair 路径
显式确认后才删。

Revision ID: p21_w37_kb_consistency
Revises: p21_w37_eval_scores
Create Date: 2027-02-07 12:00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "p21_w37_kb_consistency"
down_revision: Union[str, Sequence[str], None] = "p21_w37_eval_scores"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) kb_consistency_reports
    op.create_table(
        "kb_consistency_reports",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "kb_id",
            sa.BigInteger(),
            sa.ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("issues", sa.JSON(), nullable=True),
        sa.Column(
            "scanned_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "quarantined_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "fixed_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "error_message", sa.String(length=1024), nullable=True
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "finished_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_kb_consistency_kb_started",
        "kb_consistency_reports",
        ["kb_id", "started_at"],
    )

    # 2) chunks 加 quarantine 字段
    op.add_column(
        "chunks",
        sa.Column(
            "quarantined",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "chunks",
        sa.Column(
            "quarantine_reason", sa.String(length=64), nullable=True
        ),
    )
    op.create_index(
        "ix_chunks_quarantined", "chunks", ["quarantined"]
    )


def downgrade() -> None:
    op.drop_index("ix_chunks_quarantined", table_name="chunks")
    op.drop_column("chunks", "quarantine_reason")
    op.drop_column("chunks", "quarantined")
    op.drop_index(
        "ix_kb_consistency_kb_started", table_name="kb_consistency_reports"
    )
    op.drop_table("kb_consistency_reports")
