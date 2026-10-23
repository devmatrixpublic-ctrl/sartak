"""payments.amount_band replaces payments.amount

Revision ID: d4e9b6a3c812
Revises: c1a8f3d20e57
Create Date: 2026-10-23 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd4e9b6a3c812'
down_revision: Union[str, Sequence[str], None] = 'c1a8f3d20e57'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

BAND_SQL = (
    "CASE WHEN amount < 500 THEN 'lt_500' WHEN amount < 2000 THEN '500_2k' WHEN amount < 10000 THEN '2k_10k' "
    "WHEN amount < 50000 THEN '10k_50k' WHEN amount < 200000 THEN '50k_2l' ELSE 'gt_2l' END"
)


def upgrade() -> None:
    with op.batch_alter_table('payments') as batch:
        batch.add_column(sa.Column('amount_band', sa.String(length=16), nullable=True))
    op.execute(f"UPDATE payments SET amount_band = {BAND_SQL}")
    with op.batch_alter_table('payments') as batch:
        batch.alter_column('amount_band', existing_type=sa.String(length=16), nullable=False)
        batch.drop_column('amount')


def downgrade() -> None:
    # The rupee amount is gone for good; a restored column holds the band's lower bound, not the real amount.
    with op.batch_alter_table('payments') as batch:
        batch.add_column(sa.Column('amount', sa.Float(), nullable=True))
    op.execute(
        "UPDATE payments SET amount = CASE amount_band WHEN 'lt_500' THEN 0.01 WHEN '500_2k' THEN 500 "
        "WHEN '2k_10k' THEN 2000 WHEN '10k_50k' THEN 10000 WHEN '50k_2l' THEN 50000 ELSE 200000 END"
    )
    with op.batch_alter_table('payments') as batch:
        batch.alter_column('amount', existing_type=sa.Float(), nullable=False)
        batch.drop_column('amount_band')
