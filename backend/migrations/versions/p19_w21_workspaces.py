"""P19.3: workspaces / teams / memberships / workspace_quotas 4 张新表
+ 10 张业务表加 workspace_id (NULLABLE, FK → workspaces.id) + 老数据 backfill
+ default workspace (id=1) 幂等 seed

红线：workspace_id 全 NULLABLE + 默认 backfill 到 1 —— 老 API 零迁移升级

Revision ID: p19_w21_workspaces
Revises: p19_w19_plugins
Create Date: 2026-05-23 12:00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "p19_w21_workspaces"
down_revision: Union[str, Sequence[str], None] = "p19_w19_plugins"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# 业务表清单：要加 workspace_id NULLABLE FK 的顶层资源表
_BIZ_TABLES = (
    "agents",
    "apps",
    "knowledge_bases",
    "graphs",
    "datasets",
    "eval_jobs",
    "tool_instances",
    "channels",
    "abilities",
    "embed_configs",
)

_DEFAULT_WS_ID = 1


def upgrade() -> None:
    # ── 4 张新表 ────────────────────────────────────────
    op.create_table(
        "workspaces",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "workspace_key", sa.String(length=64), nullable=False, unique=True
        ),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column(
            "plan",
            sa.String(length=16),
            nullable=False,
            server_default="free",
        ),
        sa.Column("config", sa.JSON(), nullable=True),
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
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "teams",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "workspace_id",
            sa.BigInteger(),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=128), nullable=False),
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
    op.create_index("ix_teams_workspace", "teams", ["workspace_id"])

    op.create_table(
        "memberships",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "workspace_id",
            sa.BigInteger(),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "team_id",
            sa.BigInteger(),
            sa.ForeignKey("teams.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "user_id",
            "workspace_id",
            "team_id",
            name="uq_memberships_user_ws_team",
        ),
    )
    op.create_index("ix_memberships_user", "memberships", ["user_id"])
    op.create_index(
        "ix_memberships_workspace", "memberships", ["workspace_id"]
    )

    op.create_table(
        "workspace_quotas",
        sa.Column(
            "workspace_id",
            sa.BigInteger(),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("token_quota_monthly", sa.BigInteger(), nullable=True),
        sa.Column(
            "token_used_current_month",
            sa.BigInteger(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("request_quota_daily", sa.BigInteger(), nullable=True),
        sa.Column(
            "request_used_today",
            sa.BigInteger(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "reset_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # ── default workspace seed (id=1) ─────────────────
    # 幂等：用 ON CONFLICT 防重复执行（虽然全新表，但加保险）
    op.execute(
        sa.text(
            f"""
            INSERT INTO workspaces (id, workspace_key, name, plan)
            VALUES ({_DEFAULT_WS_ID}, 'default', '默认工作区', 'enterprise')
            ON CONFLICT (id) DO NOTHING
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            INSERT INTO workspace_quotas (workspace_id, reset_at)
            VALUES ({_DEFAULT_WS_ID}, NOW())
            ON CONFLICT (workspace_id) DO NOTHING
            """
        )
    )

    # ── 业务表加 workspace_id (NULLABLE, FK, INDEX) + backfill ──
    for tbl in _BIZ_TABLES:
        op.add_column(
            tbl,
            sa.Column(
                "workspace_id",
                sa.BigInteger(),
                sa.ForeignKey(
                    "workspaces.id", ondelete="SET NULL", name=f"fk_{tbl}_workspace"
                ),
                nullable=True,
            ),
        )
        op.create_index(f"ix_{tbl}_workspace", tbl, ["workspace_id"])
        op.execute(
            sa.text(
                f"UPDATE {tbl} SET workspace_id = {_DEFAULT_WS_ID} "
                "WHERE workspace_id IS NULL"
            )
        )


def downgrade() -> None:
    for tbl in _BIZ_TABLES:
        op.drop_index(f"ix_{tbl}_workspace", table_name=tbl)
        op.drop_constraint(f"fk_{tbl}_workspace", tbl, type_="foreignkey")
        op.drop_column(tbl, "workspace_id")
    op.drop_table("workspace_quotas")
    op.drop_index("ix_memberships_workspace", table_name="memberships")
    op.drop_index("ix_memberships_user", table_name="memberships")
    op.drop_table("memberships")
    op.drop_index("ix_teams_workspace", table_name="teams")
    op.drop_table("teams")
    op.drop_table("workspaces")
