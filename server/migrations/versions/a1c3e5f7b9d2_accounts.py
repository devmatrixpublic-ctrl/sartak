"""accounts (phone-number identity, stored as a keyed hash) and devices.account_id

Revision ID: a1c3e5f7b9d2
Revises: f7c2d8b51a94
Create Date: 2026-10-25 06:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1c3e5f7b9d2'
down_revision: Union[str, Sequence[str], None] = 'f7c2d8b51a94'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'accounts',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('phone_hash', sa.String(length=64), nullable=False),
        sa.Column('name', sa.String(length=60), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_accounts_phone_hash', 'accounts', ['phone_hash'], unique=True)
    with op.batch_alter_table('devices') as batch:
        batch.add_column(sa.Column('account_id', sa.String(length=36), nullable=True))
        batch.create_index('ix_devices_account_id', ['account_id'])
        batch.create_foreign_key('fk_devices_account_id', 'accounts', ['account_id'], ['id'])


def downgrade() -> None:
    with op.batch_alter_table('devices') as batch:
        batch.drop_constraint('fk_devices_account_id', type_='foreignkey')
        batch.drop_index('ix_devices_account_id')
        batch.drop_column('account_id')
    op.drop_index('ix_accounts_phone_hash', table_name='accounts')
    op.drop_table('accounts')
