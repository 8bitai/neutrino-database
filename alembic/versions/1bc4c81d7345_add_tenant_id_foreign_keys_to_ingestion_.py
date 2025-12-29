"""add tenant_id foreign keys to ingestion tables

Revision ID: [new_id]
Revises: 8a6d3f313f43
Create Date: 2025-12-29
"""
from alembic import op
import sqlalchemy as sa

revision = '1bc4c81d7345'
down_revision = '8a6d3f313f43'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add FK constraints to all ingestion tables

    # 1. datasources.tenant_id -> tenant.id
    op.create_foreign_key(
        'fk_datasources_tenant_id',
        'datasources',
        'tenant',
        ['tenant_id'],
        ['id'],
        ondelete='CASCADE'
    )

    # 2. files.tenant_id -> tenant.id
    op.create_foreign_key(
        'fk_files_tenant_id',
        'files',
        'tenant',
        ['tenant_id'],
        ['id'],
        ondelete='CASCADE'
    )

    # 3. ingestion_jobs.tenant_id -> tenant.id
    op.create_foreign_key(
        'fk_ingestion_jobs_tenant_id',
        'ingestion_jobs',
        'tenant',
        ['tenant_id'],
        ['id'],
        ondelete='CASCADE'
    )

    # 4. parsing.tenant_id -> tenant.id
    op.create_foreign_key(
        'fk_parsing_tenant_id',
        'parsing',
        'tenant',
        ['tenant_id'],
        ['id'],
        ondelete='CASCADE'
    )

    # 5. chunk.tenant_id -> tenant.id
    op.create_foreign_key(
        'fk_chunk_tenant_id',
        'chunk',
        'tenant',
        ['tenant_id'],
        ['id'],
        ondelete='CASCADE'
    )

    # 6. embedding.tenant_id -> tenant.id
    op.create_foreign_key(
        'fk_embedding_tenant_id',
        'embedding',
        'tenant',
        ['tenant_id'],
        ['id'],
        ondelete='CASCADE'
    )

    # 7. index_sync.tenant_id -> tenant.id
    op.create_foreign_key(
        'fk_index_sync_tenant_id',
        'index_sync',
        'tenant',
        ['tenant_id'],
        ['id'],
        ondelete='CASCADE'
    )

    # 8. strategies.tenant_id -> tenant.id
    op.create_foreign_key(
        'fk_strategies_tenant_id',
        'strategies',
        'tenant',
        ['tenant_id'],
        ['id'],
        ondelete='CASCADE'
    )


def downgrade() -> None:
    # Drop FK constraints in reverse order
    op.drop_constraint('fk_strategies_tenant_id', 'strategies', type_='foreignkey')
    op.drop_constraint('fk_index_sync_tenant_id', 'index_sync', type_='foreignkey')
    op.drop_constraint('fk_embedding_tenant_id', 'embedding', type_='foreignkey')
    op.drop_constraint('fk_chunk_tenant_id', 'chunk', type_='foreignkey')
    op.drop_constraint('fk_parsing_tenant_id', 'parsing', type_='foreignkey')
    op.drop_constraint('fk_ingestion_jobs_tenant_id', 'ingestion_jobs', type_='foreignkey')
    op.drop_constraint('fk_files_tenant_id', 'files', type_='foreignkey')
    op.drop_constraint('fk_datasources_tenant_id', 'datasources', type_='foreignkey')