"""chunks 增加段落级管理字段（enabled / keywords / hit_count）

KB-P3：段落级 chunk 交互。
- enabled：用户显式启停（默认 true）；enabled=false 不参与检索。与 quarantined
  区分——quarantined 是一致性扫描的半软删（repair 物理删），enabled 是用户开关。
- keywords：人工/自动关键词（JSON list）。
- hit_count：检索命中累加计数。

Revision ID: p23_w59_chunk_segment_mgmt
Revises: p23_w58_agent_model_bindings
Create Date: 2026-05-26 13:50:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "p23_w59_chunk_segment_mgmt"
down_revision: Union[str, Sequence[str], None] = "p23_w58_agent_model_bindings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "chunks",
        sa.Column(
            "enabled", sa.Boolean(), nullable=False, server_default="true"
        ),
    )
    op.add_column("chunks", sa.Column("keywords", sa.JSON(), nullable=True))
    op.add_column(
        "chunks",
        sa.Column("hit_count", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("chunks", "hit_count")
    op.drop_column("chunks", "keywords")
    op.drop_column("chunks", "enabled")
