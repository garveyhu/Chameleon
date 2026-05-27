"""块5: 移除多租户 Workspaces，系统降为单租户

[SCHEMA-CHANGE] 删除多租户层：workspaces / workspace_groups / teams /
memberships / workspace_quotas 五表 + 各业务表 workspace_id 列 +
call_logs.group_ratio 列。

配额 / 限流（WorkspaceQuota + 预扣）整套删，按 key 的配额以后在 Key 管理重做；
分组计费倍率 group_ratio 整个删，计费 = 原始 cost_usd（不再乘倍率）。

eval_templates 的唯一约束从 (workspace_id, name, version) 改为 (name, version)。

Revision ID: p24_w67_drop_workspaces
Revises: p24_w66_drop_model_gateway
Create Date: 2026-05-27 17:45:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "p24_w67_drop_workspaces"
down_revision: Union[str, Sequence[str], None] = "p24_w66_drop_model_gateway"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


#: 业务表：p19_w21 加 workspace_id（NULLABLE FK），带 ix_<tbl>_workspace 索引
#: + fk_<tbl>_workspace 外键。channels / abilities 已在 p24_w66 删表，不含。
_BIZ_TABLES = (
    "agents",
    "apps",
    "knowledge_bases",
    "graphs",
    "datasets",
    "eval_jobs",
    "tool_instances",
    "embed_configs",
)


def upgrade() -> None:
    # 1. 业务表 workspace_id 列（带 ix_<tbl>_workspace + fk_<tbl>_workspace）
    for tbl in _BIZ_TABLES:
        op.drop_index(f"ix_{tbl}_workspace", table_name=tbl)
        op.drop_constraint(f"fk_{tbl}_workspace", tbl, type_="foreignkey")
        op.drop_column(tbl, "workspace_id")

    # 2. audit_logs.workspace_id（ix_audit_logs_workspace + fk_audit_logs_workspace）
    op.drop_index("ix_audit_logs_workspace", table_name="audit_logs")
    op.drop_constraint(
        "fk_audit_logs_workspace", "audit_logs", type_="foreignkey"
    )
    op.drop_column("audit_logs", "workspace_id")

    # 3. app_templates.workspace_id（无独立索引，FK 由 PG 自动连带）
    op.drop_column("app_templates", "workspace_id")

    # 4. eval_templates：唯一约束 (workspace_id, name, version) → (name, version)
    op.drop_constraint(
        "uq_eval_templates_ws_name_ver", "eval_templates", type_="unique"
    )
    op.drop_column("eval_templates", "workspace_id")
    op.create_unique_constraint(
        "uq_eval_templates_name_ver",
        "eval_templates",
        ["name", "version"],
    )

    # 5. call_logs.group_ratio（分组计费倍率，整删）
    op.drop_column("call_logs", "group_ratio")

    # 6. 删多租户 5 表（FK 依赖顺序：先依赖方，后被依赖方）
    #    memberships → teams + workspaces；teams → workspaces；
    #    workspace_quotas → workspaces；workspaces.group_code → workspace_groups
    op.drop_table("memberships")
    op.drop_table("teams")
    op.drop_table("workspace_quotas")
    op.drop_table("workspaces")
    op.drop_table("workspace_groups")


def downgrade() -> None:
    # best-effort 重建结构（不恢复数据）。建表顺序与 upgrade 删表相反：
    # 先 workspace_groups（被 workspaces.group_code 引用），再 workspaces，
    # 再 teams / memberships / workspace_quotas。

    op.create_table(
        "workspace_groups",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column(
            "ratio", sa.Numeric(6, 3), nullable=False, server_default="1.000"
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
        sa.UniqueConstraint("code", name="uq_workspace_groups_code"),
    )

    op.create_table(
        "workspaces",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "workspace_key", sa.String(length=64), nullable=False, unique=True
        ),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column(
            "plan", sa.String(length=16), nullable=False, server_default="free"
        ),
        sa.Column(
            "group_code",
            sa.String(length=32),
            sa.ForeignKey(
                "workspace_groups.code",
                ondelete="SET NULL",
                name="fk_workspaces_group_code",
            ),
            nullable=True,
            server_default="default",
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
            "user_id", "workspace_id", "team_id", name="uq_memberships_user_ws_team"
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

    # call_logs.group_ratio 回填
    op.add_column(
        "call_logs",
        sa.Column("group_ratio", sa.Numeric(6, 3), nullable=True),
    )

    # eval_templates：约束回退到含 workspace_id
    op.drop_constraint(
        "uq_eval_templates_name_ver", "eval_templates", type_="unique"
    )
    op.add_column(
        "eval_templates",
        sa.Column(
            "workspace_id",
            sa.BigInteger(),
            sa.ForeignKey("workspaces.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_unique_constraint(
        "uq_eval_templates_ws_name_ver",
        "eval_templates",
        ["workspace_id", "name", "version"],
    )

    # app_templates.workspace_id 回填
    op.add_column(
        "app_templates",
        sa.Column(
            "workspace_id",
            sa.BigInteger(),
            sa.ForeignKey("workspaces.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )

    # audit_logs.workspace_id 回填
    op.add_column(
        "audit_logs",
        sa.Column("workspace_id", sa.BigInteger(), nullable=True),
    )
    op.create_foreign_key(
        "fk_audit_logs_workspace",
        "audit_logs",
        "workspaces",
        ["workspace_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_audit_logs_workspace", "audit_logs", ["workspace_id"])

    # 业务表 workspace_id 回填（带 ix + fk）
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
