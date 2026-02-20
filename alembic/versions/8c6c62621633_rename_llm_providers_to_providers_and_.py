"""rename llm_providers to providers and add provider_category

Revision ID: 8c6c62621633
Revises: 0c58a37d67b7
Create Date: 2026-02-20 10:07:51.433739

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8c6c62621633'
down_revision: Union[str, Sequence[str], None] = '0c58a37d67b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    # Step 1: Rename table
    op.rename_table('llm_providers', 'providers')

    # Step 2: Add provider_category column (temporarily nullable)
    op.add_column('providers', sa.Column('provider_category', sa.String(length=50), nullable=True))

    # Step 3: Backfill existing rows with 'llm' category
    op.execute("UPDATE providers SET provider_category = 'llm' WHERE provider_category IS NULL")

    # Step 4: Make provider_category NOT NULL
    op.alter_column('providers', 'provider_category', nullable=False)



def downgrade() -> None:
    """Downgrade schema."""

    # Step 1: Drop provider_category column
    op.drop_column('providers', 'provider_category')

    # Step 2: Rename table back
    op.rename_table('providers', 'llm_providers')
