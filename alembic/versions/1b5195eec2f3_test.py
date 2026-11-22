"""test

Revision ID: 1b5195eec2f3
Revises: 0fe5811dcd77
Create Date: 2026-09-30 12:13:58.877262

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1b5195eec2f3'
down_revision: Union[str, Sequence[str], None] = '0fe5811dcd77'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
