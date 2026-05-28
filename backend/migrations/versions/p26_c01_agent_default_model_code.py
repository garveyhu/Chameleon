"""agents.default_model_id → default_model_code（用 model.code 字符串 key 替代 FK id）

[SCHEMA-CHANGE] 默认模型绑定从 FK id 改成 model.code（跟 model_bindings JSON
里的 key 风格一致；跨环境迁移 / 重建模型表时不会断引用；trace 链路少查一跳）。

迁移步骤：
1. ADD agents.default_model_code VARCHAR(64) NULL
2. 回填：UPDATE agents SET default_model_code = models.code FROM models
   WHERE agents.default_model_id = models.id
3. DROP agents.default_model_id（去 FK 约束）

Revision ID: p26_c01_agent_default_model_code
Revises: p26_b01_msg_request_id
Create Date: 2026-05-29 01:30:00
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op


revision: str = "p26_c01_agent_default_model_code"
down_revision: Union[str, Sequence[str], None] = "p26_b01_msg_request_id"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agents",
        sa.Column(
            "default_model_code",
            sa.String(length=64),
            nullable=True,
            comment="默认模型 code（'qwen-plus' 这种品牌名 key）；替代 default_model_id FK",
        ),
    )
    # 回填：从现有 default_model_id 查 models.code
    op.execute(
        """
        UPDATE agents
        SET default_model_code = m.code
        FROM models m
        WHERE agents.default_model_id = m.id
          AND agents.default_model_id IS NOT NULL
        """
    )
    # 删 FK 约束 + 列
    op.drop_constraint("agents_default_model_id_fkey", "agents", type_="foreignkey")
    op.drop_column("agents", "default_model_id")


def downgrade() -> None:
    op.add_column(
        "agents",
        sa.Column("default_model_id", sa.BigInteger(), nullable=True),
    )
    op.execute(
        """
        UPDATE agents
        SET default_model_id = m.id
        FROM models m
        WHERE agents.default_model_code = m.code
          AND agents.default_model_code IS NOT NULL
        """
    )
    op.create_foreign_key(
        "agents_default_model_id_fkey",
        "agents",
        "models",
        ["default_model_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.drop_column("agents", "default_model_code")
