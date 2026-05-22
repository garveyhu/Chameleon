"""P16-E2: call_logs 加 spans / request_payload / response_payload

Revision ID: p16e2_spans
Revises: p16c4_chunks_tsv
Create Date: 2026-05-22 23:00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "p16e2_spans"
down_revision: Union[str, Sequence[str], None] = "p16c4_chunks_tsv"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("call_logs", sa.Column("spans", sa.JSON(), nullable=True))
    op.add_column(
        "call_logs", sa.Column("request_payload", sa.JSON(), nullable=True)
    )
    op.add_column(
        "call_logs", sa.Column("response_payload", sa.JSON(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("call_logs", "response_payload")
    op.drop_column("call_logs", "request_payload")
    op.drop_column("call_logs", "spans")
