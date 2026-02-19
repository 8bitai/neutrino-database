"""add llm providers table

Revision ID: 0c58a37d67b7
Revises: c4abbcc55cb8
Create Date: 2026-02-11 18:19:26.212088

"""
from typing import Sequence, Union
from sqlalchemy.dialects.postgresql import JSONB
from alembic import op
import sqlalchemy as sa
import uuid

# revision identifiers, used by Alembic.
revision: str = '0c58a37d67b7'
down_revision: Union[str, Sequence[str], None] = 'c4abbcc55cb8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create the llm_providers table
    op.create_table(
        'llm_providers',
        sa.Column('id', sa.UUID(), nullable=False, default=uuid.uuid4),
        sa.Column('workspace_id', sa.UUID(), nullable=False),
        sa.Column('service_type', sa.String(50), nullable=False),
        sa.Column('display_name', sa.String(255), nullable=False),
        sa.Column('encrypted_value', sa.Text(), nullable=False),
        sa.Column('encryption_method', sa.String(50), nullable=False, server_default=sa.text("'AES-256-GCM'")),
        sa.Column('connection_config', JSONB(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column('model_config', JSONB(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('created_by', sa.UUID(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspace.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['user.id'], ondelete='SET NULL'),
        sa.UniqueConstraint('workspace_id', 'service_type', 'display_name', name='ux_llm_provider')
    )

    # Create indexes
    op.create_index('ix_llm_providers_workspace', 'llm_providers', ['workspace_id'])
    op.create_index('ix_llm_providers_service_active', 'llm_providers', ['service_type', 'is_active'])
    op.create_index('ix_llm_providers_workspace_service', 'llm_providers', ['workspace_id', 'service_type'])


def downgrade() -> None:
    # Drop indexes
    op.drop_index('ix_llm_providers_workspace_service', table_name='llm_providers')
    op.drop_index('ix_llm_providers_service_active', table_name='llm_providers')
    op.drop_index('ix_llm_providers_workspace', table_name='llm_providers')

    # Drop table
    op.drop_table('llm_providers')