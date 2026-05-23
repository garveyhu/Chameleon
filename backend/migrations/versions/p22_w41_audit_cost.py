"""P22.1 PR #71: audit_logs 11 维 + call_logs.cost_usd + model_pricing 表

Revision ID: p22_w41_audit_cost
Revises: p21_w37_kb_consistency
Create Date: 2027-03-01 12:00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "p22_w41_audit_cost"
down_revision: Union[str, Sequence[str], None] = "p21_w37_kb_consistency"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) audit_logs 加 2 列（9 → 11 维）
    op.add_column(
        "audit_logs",
        sa.Column("workspace_id", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "audit_logs",
        sa.Column("session_id", sa.String(length=64), nullable=True),
    )
    op.create_foreign_key(
        "fk_audit_logs_workspace",
        "audit_logs",
        "workspaces",
        ["workspace_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_audit_logs_workspace", "audit_logs", ["workspace_id"]
    )

    # 2) call_logs 加 cost_usd
    op.add_column(
        "call_logs",
        sa.Column("cost_usd", sa.Numeric(precision=12, scale=6), nullable=True),
    )

    # 3) model_pricing 表
    op.create_table(
        "model_pricing",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("model_code", sa.String(length=64), nullable=False),
        sa.Column(
            "effective_from", sa.DateTime(timezone=True), nullable=False
        ),
        sa.Column(
            "prompt_price_per_1k",
            sa.Numeric(precision=10, scale=6),
            nullable=False,
        ),
        sa.Column(
            "completion_price_per_1k",
            sa.Numeric(precision=10, scale=6),
            nullable=False,
        ),
        sa.Column(
            "currency",
            sa.String(length=8),
            nullable=False,
            server_default="USD",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "model_code", "effective_from", name="uq_model_pricing_code_ts"
        ),
    )
    op.create_index(
        "ix_model_pricing_code_effective",
        "model_pricing",
        ["model_code", "effective_from"],
    )


def downgrade() -> None:
    op.drop_index("ix_model_pricing_code_effective", table_name="model_pricing")
    op.drop_table("model_pricing")
    op.drop_column("call_logs", "cost_usd")
    op.drop_index("ix_audit_logs_workspace", table_name="audit_logs")
    op.drop_constraint(
        "fk_audit_logs_workspace", "audit_logs", type_="foreignkey"
    )
    op.drop_column("audit_logs", "session_id")
    op.drop_column("audit_logs", "workspace_id")
