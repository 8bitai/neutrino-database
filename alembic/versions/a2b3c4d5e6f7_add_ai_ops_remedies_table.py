"""add_ai_ops_remedies_table

Revision ID: a2b3c4d5e6f7
Revises: f7a8b3c2d1e0
Create Date: 2026-03-23 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'a2b3c4d5e6f7'
down_revision: Union[str, Sequence[str], None] = 'f7a8b3c2d1e0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add ai_ops_remedies table for storing AI-generated incident remedies."""
    op.create_table(
        'ai_ops_remedies',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('tenant_id', sa.UUID(as_uuid=False), nullable=False),
        sa.Column('incident_id', sa.String(length=255), nullable=True),
        sa.Column('team', sa.String(length=255), nullable=True),
        sa.Column('priority', sa.String(length=50), nullable=True),
        sa.Column('incident_title', sa.String(length=500), nullable=False),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('root_cause', sa.Text(), nullable=True),
        sa.Column('email_subject', sa.String(length=500), nullable=True),
        sa.Column('status', sa.String(length=50), server_default=sa.text("'active'"), nullable=False),
        sa.Column('incident_timestamp', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('remedy', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenant.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_ai_ops_remedies_tenant', 'ai_ops_remedies', ['tenant_id'], unique=False)
    op.create_index('ix_ai_ops_remedies_tenant_status', 'ai_ops_remedies', ['tenant_id', 'status'], unique=False)
    op.create_index('ix_ai_ops_remedies_tenant_timestamp', 'ai_ops_remedies', ['tenant_id', 'incident_timestamp'], unique=False)


def downgrade() -> None:
    """Drop ai_ops_remedies table."""
    op.drop_index('ix_ai_ops_remedies_tenant_timestamp', table_name='ai_ops_remedies')
    op.drop_index('ix_ai_ops_remedies_tenant_status', table_name='ai_ops_remedies')
    op.drop_index('ix_ai_ops_remedies_tenant', table_name='ai_ops_remedies')
    op.drop_table('ai_ops_remedies')
