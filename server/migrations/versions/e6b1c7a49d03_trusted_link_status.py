"""trusted_links.status (pending | accepted | revoked)

Revision ID: e6b1c7a49d03
Revises: d4e9b6a3c812
Create Date: 2026-10-24 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e6b1c7a49d03'
down_revision: Union[str, Sequence[str], None] = 'd4e9b6a3c812'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Links that already exist were made before contacts could answer; keep them working as accepted.
    with op.batch_alter_table('trusted_links') as batch:
        batch.add_column(sa.Column('status', sa.String(length=16), nullable=False, server_default='accepted'))
    with op.batch_alter_table('trusted_links') as batch:
        batch.alter_column('status', existing_type=sa.String(length=16), server_default=None)


def downgrade() -> None:
    with op.batch_alter_table('trusted_links') as batch:
        batch.drop_column('status')
