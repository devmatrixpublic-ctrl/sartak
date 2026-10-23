"""payment hold reason, trusted-contact decision, payee index

Revision ID: b7d2e4f9a1c3
Revises: a3c91d7e5b20
Create Date: 2026-10-23 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b7d2e4f9a1c3'
down_revision: Union[str, Sequence[str], None] = 'a3c91d7e5b20'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('payments', sa.Column('hold_reason', sa.String(length=32), nullable=True))
    op.add_column('payments', sa.Column('decided_by_device_id', sa.String(length=36), nullable=True))
    op.add_column('payments', sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True))
    op.create_index(op.f('ix_payments_payee_hash'), 'payments', ['payee_hash'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_payments_payee_hash'), table_name='payments')
    op.drop_column('payments', 'decided_at')
    op.drop_column('payments', 'decided_by_device_id')
    op.drop_column('payments', 'hold_reason')
