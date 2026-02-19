"""Add strategy_id to strategies table

Revision ID: 697a0beacb82
Revises: d8d0e43019ac
Create Date: 2025-12-02 15:10:31.600966

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '697a0beacb82'
down_revision: Union[str, Sequence[str], None] = 'd8d0e43019ac'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Add strategy_id column to strategies table.
    """
    # Add the column
    op.add_column('strategies', sa.Column('strategy_id', sa.UUID(), nullable=True))

    # Backfill existing records with random UUIDs
    op.execute("""
        UPDATE strategies 
        SET strategy_id = gen_random_uuid() 
        WHERE strategy_id IS NULL
    """)

    op.alter_column('strategies', 'strategy_id', nullable=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('strategies', 'strategy_id')