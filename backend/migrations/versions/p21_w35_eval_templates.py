"""P21.2: eval_templates 表 + eval_jobs 加 template_id/template_version_frozen

业务：评判模板复用 + 版本化。template.version 自增；老 EvalJob 引用
template_version_frozen 不变（行为可预期）。

Revision ID: p21_w35_eval_templates
Revises: p20_w29_kb_collections
Create Date: 2027-01-17 12:00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "p21_w35_eval_templates"
down_revision: Union[str, Sequence[str], None] = "p20_w29_kb_collections"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "eval_templates",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("judge_provider", sa.String(length=64), nullable=True),
        sa.Column(
            "version",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
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
        sa.UniqueConstraint(
            "workspace_id",
            "name",
            "version",
            name="uq_eval_templates_ws_name_ver",
        ),
    )

    # eval_jobs 加 2 列
    op.add_column(
        "eval_jobs",
        sa.Column("template_id", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "eval_jobs",
        sa.Column("template_version_frozen", sa.BigInteger(), nullable=True),
    )
    op.create_foreign_key(
        "fk_eval_jobs_template",
        "eval_jobs",
        "eval_templates",
        ["template_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_eval_jobs_template", "eval_jobs", type_="foreignkey"
    )
    op.drop_column("eval_jobs", "template_version_frozen")
    op.drop_column("eval_jobs", "template_id")
    op.drop_table("eval_templates")
