"""P19.2: plugin_instances 表

业务：admin 安装的 plugin（provider/tool/embedding）实例 + 用户配置。
builtin 列（local/dify/fastgpt）由首次启动 seed，source='builtin'。

Revision ID: p19_w19_plugins
Revises: p19_w17_eval_jobs
Create Date: 2026-05-23 11:30:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "p19_w19_plugins"
down_revision: Union[str, Sequence[str], None] = "p19_w17_eval_jobs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "plugin_instances",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "plugin_key", sa.String(length=64), nullable=False, unique=True
        ),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("type", sa.String(length=16), nullable=False),
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column(
            "source",
            sa.String(length=32),
            nullable=False,
            server_default="local",
        ),
        sa.Column("source_url", sa.String(length=512), nullable=True),
        sa.Column("manifest", sa.JSON(), nullable=False),
        sa.Column(
            "config",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'::json"),
        ),
        sa.Column(
            "enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "installed_at",
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
    op.create_index(
        "ix_plugin_instances_type_enabled",
        "plugin_instances",
        ["type", "enabled"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_plugin_instances_type_enabled", table_name="plugin_instances"
    )
    op.drop_table("plugin_instances")
