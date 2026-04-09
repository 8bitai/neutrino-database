"""add product column to underwriting_rules

Revision ID: 0e2ffac974b4
Revises: f2a3b4c5d6e7
Create Date: 2026-04-09 12:43:55.085532

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0e2ffac974b4'
down_revision: Union[str, Sequence[str], None] = 'f2a3b4c5d6e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name='underwriting_rules' AND column_name='product'"
    ))
    if not result.fetchone():
        op.add_column('underwriting_rules', sa.Column('product', sa.Text(), nullable=False, server_default='All'))


def downgrade() -> None:
    op.drop_column('underwriting_rules', 'product')
