"""alerts.review_status and audit_log

Revision ID: f7c2d8b51a94
Revises: e6b1c7a49d03
Create Date: 2026-10-24 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f7c2d8b51a94'
down_revision: Union[str, Sequence[str], None] = 'e6b1c7a49d03'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('alerts') as batch:
        batch.add_column(sa.Column('review_status', sa.String(length=16), nullable=False, server_default='open'))
    with op.batch_alter_table('alerts') as batch:
        batch.alter_column('review_status', existing_type=sa.String(length=16), server_default=None)
    op.create_table(
        'audit_log',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('actor_device_id', sa.String(length=36), nullable=False),
        sa.Column('action', sa.String(length=32), nullable=False),
        sa.Column('alert_id', sa.String(length=36), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_audit_log_actor_device_id'), 'audit_log', ['actor_device_id'], unique=False)
    op.create_index(op.f('ix_audit_log_alert_id'), 'audit_log', ['alert_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_audit_log_alert_id'), table_name='audit_log')
    op.drop_index(op.f('ix_audit_log_actor_device_id'), table_name='audit_log')
    op.drop_table('audit_log')
    with op.batch_alter_table('alerts') as batch:
        batch.drop_column('review_status')
