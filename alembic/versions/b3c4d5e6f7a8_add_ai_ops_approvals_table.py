"""Add ai_ops_approvals table

Revision ID: b3c4d5e6f7a8
Revises: a2b3c4d5e6f7
Create Date: 2026-03-23 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'b3c4d5e6f7a8'
down_revision: Union[str, Sequence[str], None] = 'a2b3c4d5e6f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'ai_ops_approvals',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=False), sa.ForeignKey('tenant.id', ondelete='CASCADE'), nullable=False),
        sa.Column('remedy_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('ai_ops_remedies.id', ondelete='CASCADE'), nullable=False),
        sa.Column('decision', sa.String(50), nullable=False),
        sa.Column('decided_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_unique_constraint('uq_ai_ops_approvals_remedy', 'ai_ops_approvals', ['remedy_id'])
    op.create_index('ix_ai_ops_approvals_tenant', 'ai_ops_approvals', ['tenant_id'])
    op.create_index('ix_ai_ops_approvals_remedy', 'ai_ops_approvals', ['remedy_id'])


def downgrade() -> None:
    op.drop_index('ix_ai_ops_approvals_remedy', table_name='ai_ops_approvals')
    op.drop_index('ix_ai_ops_approvals_tenant', table_name='ai_ops_approvals')
    op.drop_constraint('uq_ai_ops_approvals_remedy', 'ai_ops_approvals', type_='unique')
    op.drop_table('ai_ops_approvals')
