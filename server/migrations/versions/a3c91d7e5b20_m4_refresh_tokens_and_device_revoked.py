"""m4: refresh_tokens table and devices.revoked

Revision ID: a3c91d7e5b20
Revises: ef04b65f1726
Create Date: 2026-10-21 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a3c91d7e5b20'
down_revision: Union[str, Sequence[str], None] = 'ef04b65f1726'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('devices', sa.Column('revoked', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_table(
        'refresh_tokens',
        sa.Column('token_hash', sa.String(length=64), nullable=False),
        sa.Column('device_id', sa.String(length=36), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('used', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['device_id'], ['devices.id']),
        sa.PrimaryKeyConstraint('token_hash'),
    )
    op.create_index(op.f('ix_refresh_tokens_device_id'), 'refresh_tokens', ['device_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_refresh_tokens_device_id'), table_name='refresh_tokens')
    op.drop_table('refresh_tokens')
    op.drop_column('devices', 'revoked')
