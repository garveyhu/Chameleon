"""merge agentkit x08 + newapi x09 heads

Revision ID: 3665cec8fcd2
Revises: p27_x08_agent_memory, p27_x09_dataset_categories
Create Date: 2026-06-09 10:23:34.794003

"""
from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = '3665cec8fcd2'
down_revision: Union[str, Sequence[str], None] = ('p27_x08_agent_memory', 'p27_x09_dataset_categories')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
