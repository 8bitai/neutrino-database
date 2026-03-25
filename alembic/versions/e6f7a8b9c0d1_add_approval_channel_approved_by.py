"""Add ai_ops_sops, ai_ops_workflows tables and approval columns

Revision ID: e6f7a8b9c0d1
Revises: b3c4d5e6f7a8
Create Date: 2026-03-24 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'e6f7a8b9c0d1'
down_revision: Union[str, Sequence[str], None] = 'b3c4d5e6f7a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'ai_ops_sops',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=False), sa.ForeignKey('tenant.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(500), nullable=False),
        sa.Column('content', sa.Text(), nullable=True),
        sa.Column('document_url', sa.String(1000), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_ai_ops_sops_tenant', 'ai_ops_sops', ['tenant_id'])

    op.create_table(
        'ai_ops_workflows',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=False), sa.ForeignKey('tenant.id', ondelete='CASCADE'), nullable=False),
        sa.Column('remedy_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('ai_ops_remedies.id', ondelete='CASCADE'), nullable=False),
        sa.Column('approval_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('ai_ops_approvals.id', ondelete='CASCADE'), nullable=False),
        sa.Column('status', sa.String(50), nullable=False, server_default=sa.text("'approved'")),
        sa.Column('trigger_text', sa.Text(), nullable=True),
        sa.Column('objective', sa.Text(), nullable=True),
        sa.Column('steps', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_ai_ops_workflows_tenant', 'ai_ops_workflows', ['tenant_id'])
    op.create_index('ix_ai_ops_workflows_remedy', 'ai_ops_workflows', ['remedy_id'])
    op.create_unique_constraint('uq_ai_ops_workflows_remedy', 'ai_ops_workflows', ['remedy_id'])

    op.add_column('ai_ops_approvals', sa.Column('channel', sa.String(50), nullable=True))
    op.add_column('ai_ops_approvals', sa.Column('approved_by', sa.String(500), nullable=True))


def downgrade() -> None:
    op.drop_column('ai_ops_approvals', 'approved_by')
    op.drop_column('ai_ops_approvals', 'channel')

    op.drop_constraint('uq_ai_ops_workflows_remedy', 'ai_ops_workflows', type_='unique')
    op.drop_index('ix_ai_ops_workflows_remedy', table_name='ai_ops_workflows')
    op.drop_index('ix_ai_ops_workflows_tenant', table_name='ai_ops_workflows')
    op.drop_table('ai_ops_workflows')

    op.drop_index('ix_ai_ops_sops_tenant', table_name='ai_ops_sops')
    op.drop_table('ai_ops_sops')
