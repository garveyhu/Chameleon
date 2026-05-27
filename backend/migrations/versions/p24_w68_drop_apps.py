"""块2: 移除 apps「应用容器」，归属重锚到 api_key

[SCHEMA-CHANGE] 删除应用容器层：apps / app_agents 两表。归属模型改为：
- app_id 降级为自由「调用方/来源标签」字符串，去掉所有 FK→apps（保留列 + index）；
  有 key 的调用靠 api_key_id 精确反查，无 key 的 admin/playground/eval 靠 app_id 标签兜底。
- api_keys 新增配额字段 qpm_limit / qpd_limit（从被删的 App 搬来，仅落字段不 enforce）。
- embed_configs.app_id 列（BigInt FK→apps.id）整删。

scope_type 改名（key「能访问什么」，与容器无关）：app→global、agent→app（智能体升格为应用），
kb 不变。前缀映射同步改为 global=chm_ / app=app- / kb=kbs_；旧 agent- 前缀的已签发 key
仍可用（前缀只用于生成/展示，校验靠 hash）。

去 FK 的四张表：api_keys / call_logs / conversations / tasks（列均保留为 String）。

Revision ID: p24_w68_drop_apps
Revises: p24_w67_drop_workspaces
Create Date: 2026-05-27 18:25:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "p24_w68_drop_apps"
down_revision: Union[str, Sequence[str], None] = "p24_w67_drop_workspaces"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


#: app_id FK 约束名（PG 自动命名 <table>_<col>_fkey，已用只读 pg 查询核实）。
#: 四张业务表均 FK→apps.app_key（api_keys/call_logs/conversations = CASCADE，tasks = SET NULL）。
_APP_ID_FKS = {
    "api_keys": "api_keys_app_id_fkey",
    "call_logs": "call_logs_app_id_fkey",
    "conversations": "conversations_app_id_fkey",
    "tasks": "tasks_app_id_fkey",
}


def upgrade() -> None:
    # 1. scope_type 改名（按序：app→global 先于 agent→app，避免覆盖）
    op.execute("UPDATE api_keys SET scope_type='global' WHERE scope_type='app'")
    op.execute("UPDATE api_keys SET scope_type='app' WHERE scope_type='agent'")

    # 2. api_keys 配额字段（从被删的 App 搬来；nullable）
    op.add_column("api_keys", sa.Column("qpm_limit", sa.Integer(), nullable=True))
    op.add_column("api_keys", sa.Column("qpd_limit", sa.Integer(), nullable=True))

    # 3. 删四张表的 app_id FK（保留列，列降级为自由标签字符串）
    for tbl, fk_name in _APP_ID_FKS.items():
        op.drop_constraint(fk_name, tbl, type_="foreignkey")

    # 4. embed_configs.app_id 列（先 drop index + FK，再 drop 列）
    op.drop_index("ix_embed_configs_app", table_name="embed_configs")
    op.drop_constraint(
        "embed_configs_app_id_fkey", "embed_configs", type_="foreignkey"
    )
    op.drop_column("embed_configs", "app_id")

    # 5. drop app_agents（先，FK→apps.id）再 drop apps
    op.drop_table("app_agents")
    op.drop_table("apps")


def downgrade() -> None:
    # best-effort 重建：apps / app_agents + 各表 app_id FK + embed app_id + scope_type 回退。
    # 注意：apps 被删时数据已丢，若 api_keys/call_logs/... 仍持有 orphan app_id 标签，
    # 重建 FK 会失败 —— 本 downgrade 假定在干净/可恢复数据上执行（与上一步
    # p24_w67_drop_workspaces 的 best-effort downgrade 同一约定）。

    # 1. 重建 apps
    op.create_table(
        "apps",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("app_key", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "owner_user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "status", sa.String(length=16), nullable=False, server_default="active"
        ),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.Column("qpm_limit", sa.Integer(), nullable=True),
        sa.Column("qpd_limit", sa.Integer(), nullable=True),
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
        sa.UniqueConstraint("app_key", name="apps_app_key_key"),
    )
    op.create_index("ix_apps_owner", "apps", ["owner_user_id"])

    # 2. 重建 app_agents
    op.create_table(
        "app_agents",
        sa.Column(
            "app_id",
            sa.BigInteger(),
            sa.ForeignKey("apps.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "agent_id",
            sa.BigInteger(),
            sa.ForeignKey("agents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "granted_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("granted_by_user_id", sa.BigInteger(), nullable=True),
        sa.PrimaryKeyConstraint("app_id", "agent_id", name="pk_app_agents"),
    )

    # 3. embed_configs.app_id 回填（BigInt FK→apps.id，RESTRICT）
    #    新列 nullable 以兼容历史行无对应 app（与 upgrade 删列后无法还原原值一致）
    op.add_column(
        "embed_configs",
        sa.Column("app_id", sa.BigInteger(), nullable=True),
    )
    op.create_foreign_key(
        "embed_configs_app_id_fkey",
        "embed_configs",
        "apps",
        ["app_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_embed_configs_app", "embed_configs", ["app_id"])

    # 4. 四张表 app_id FK 回建（引用 apps.app_key）
    op.create_foreign_key(
        "api_keys_app_id_fkey", "api_keys", "apps", ["app_id"], ["app_key"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "call_logs_app_id_fkey", "call_logs", "apps", ["app_id"], ["app_key"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "conversations_app_id_fkey", "conversations", "apps", ["app_id"],
        ["app_key"], ondelete="CASCADE",
    )
    op.create_foreign_key(
        "tasks_app_id_fkey", "tasks", "apps", ["app_id"], ["app_key"],
        ondelete="SET NULL",
    )

    # 5. api_keys 配额字段删除
    op.drop_column("api_keys", "qpd_limit")
    op.drop_column("api_keys", "qpm_limit")

    # 6. scope_type 回退（逆序：app→agent 先于 global→app）
    op.execute("UPDATE api_keys SET scope_type='agent' WHERE scope_type='app'")
    op.execute("UPDATE api_keys SET scope_type='app' WHERE scope_type='global'")
