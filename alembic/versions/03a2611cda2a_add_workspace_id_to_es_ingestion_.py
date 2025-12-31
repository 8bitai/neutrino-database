"""add workspace id to es-ingestion-service tables

Revision ID: 03a2611cda2a
Revises: e9aa925e4d2f
Create Date: 2025-12-31 16:20:14.394015

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '03a2611cda2a'
down_revision: Union[str, Sequence[str], None] = 'e9aa925e4d2f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - Add workspace_id to ingestion tables."""

    # Tables to modify
    tables = ['chunk', 'datasources', 'embedding', 'files', 'index_sync', 'ingestion_jobs', 'parsing', 'strategies']

    for table_name in tables:
        # Add column as NOT NULL (safe because no existing data)
        op.add_column(table_name, sa.Column('workspace_id', sa.UUID(as_uuid=False), nullable=False))

        # Add foreign key constraint with explicit name
        op.create_foreign_key(
            f'fk_{table_name}_workspace_id',
            table_name,
            'workspace',
            ['workspace_id'],
            ['id'],
            ondelete='CASCADE'
        )


def downgrade() -> None:
    """Downgrade schema - Remove workspace_id from ingestion tables."""

    tables = ['chunk', 'datasources', 'embedding', 'files', 'index_sync', 'ingestion_jobs', 'parsing', 'strategies']

    for table_name in tables:
        # Drop foreign key constraint with explicit name
        op.drop_constraint(f'fk_{table_name}_workspace_id', table_name, type_='foreignkey')

        # Drop column
        op.drop_column(table_name, 'workspace_id')