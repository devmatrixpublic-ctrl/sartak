"""payments.user_override_at

Revision ID: c1a8f3d20e57
Revises: b7d2e4f9a1c3
Create Date: 2026-10-23 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c1a8f3d20e57'
down_revision: Union[str, Sequence[str], None] = 'b7d2e4f9a1c3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('payments', sa.Column('user_override_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('payments', 'user_override_at')
