"""rename_es_index_es_doc_id_to_source_index_source_doc_id

Revision ID: f7a8b3c2d1e0
Revises: 1aee0f12ea6d
Create Date: 2026-03-18 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f7a8b3c2d1e0'
down_revision: Union[str, Sequence[str], None] = '1aee0f12ea6d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Rename es_index/es_doc_id to source_index/source_doc_id for multi-connector support."""
    op.drop_constraint('ux_ingested_logs_connector_doc', 'ingested_logs', type_='unique')
    op.alter_column('ingested_logs', 'es_index', new_column_name='source_index')
    op.alter_column('ingested_logs', 'es_doc_id', new_column_name='source_doc_id')
    op.create_unique_constraint(
        'ux_ingested_logs_connector_doc',
        'ingested_logs',
        ['connector_id', 'source_doc_id'],
    )


def downgrade() -> None:
    """Revert to es_index/es_doc_id column names."""
    op.drop_constraint('ux_ingested_logs_connector_doc', 'ingested_logs', type_='unique')
    op.alter_column('ingested_logs', 'source_index', new_column_name='es_index')
    op.alter_column('ingested_logs', 'source_doc_id', new_column_name='es_doc_id')
    op.create_unique_constraint(
        'ux_ingested_logs_connector_doc',
        'ingested_logs',
        ['connector_id', 'es_doc_id'],
    )
