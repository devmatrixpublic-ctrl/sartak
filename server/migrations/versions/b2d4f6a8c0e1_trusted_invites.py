"""trusted_invites (short codes a would-be trusted contact shows to the person they will protect)

Revision ID: b2d4f6a8c0e1
Revises: a1c3e5f7b9d2
Create Date: 2026-10-25 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b2d4f6a8c0e1'
down_revision: Union[str, Sequence[str], None] = 'a1c3e5f7b9d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'trusted_invites',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('contact_device_id', sa.String(length=36), sa.ForeignKey('devices.id'), nullable=False),
        sa.Column('code_hash', sa.String(length=64), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('used', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_trusted_invites_contact_device_id', 'trusted_invites', ['contact_device_id'])
    op.create_index('ix_trusted_invites_code_hash', 'trusted_invites', ['code_hash'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_trusted_invites_code_hash', table_name='trusted_invites')
    op.drop_index('ix_trusted_invites_contact_device_id', table_name='trusted_invites')
    op.drop_table('trusted_invites')
