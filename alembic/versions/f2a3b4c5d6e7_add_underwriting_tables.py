"""add_underwriting_tables

Revision ID: f2a3b4c5d6e7
Revises: e6144cac2db4
Create Date: 2026-04-08 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'f2a3b4c5d6e7'
down_revision: Union[str, Sequence[str], None] = 'e6144cac2db4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create underwriting tables: underwriting_sessions, underwriting_conversation_history,
    underwriting_session_documents, underwriting_pipeline_results, underwriting_rules."""

    op.create_table(
        'underwriting_sessions',
        sa.Column('session_id', sa.Text(), nullable=False),
        sa.Column('application_id', sa.Text(), nullable=False),
        sa.Column('applicant_name', sa.Text(), nullable=True),
        sa.Column('email', sa.Text(), nullable=True),
        sa.Column('address', sa.Text(), nullable=True),
        sa.Column('loan_product', sa.Text(), nullable=True),
        sa.Column('loan_amount', sa.Numeric(), nullable=True),
        sa.Column('loan_tenure_months', sa.Integer(), nullable=True),
        sa.Column('monthly_income', sa.Numeric(), nullable=True),
        sa.Column('employer_name', sa.Text(), nullable=True),
        sa.Column('loan_purpose', sa.Text(), nullable=True),
        sa.Column('dti_threshold', sa.Numeric(), nullable=True, server_default=sa.text('50')),
        sa.Column('status', sa.Text(), nullable=True),
        sa.Column('tenant_id', sa.Text(), nullable=True),
        sa.Column('chat_started_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()'), nullable=True),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()'), nullable=True),
        sa.PrimaryKeyConstraint('session_id'),
    )

    op.create_table(
        'underwriting_conversation_history',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('session_id', sa.Text(), nullable=False),
        sa.Column('turn_index', sa.Integer(), nullable=False),
        sa.Column('role', sa.Text(), nullable=False),
        sa.Column('message', sa.Text(), nullable=True),
        sa.Column('message_type', sa.Text(), nullable=True),
        sa.Column('conversation_state', sa.Text(), nullable=True),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(['session_id'], ['underwriting_sessions.session_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('session_id', 'turn_index', name='uq_underwriting_conversation_history_session_turn'),
    )
    op.create_index('ix_underwriting_conversation_history_session', 'underwriting_conversation_history', ['session_id'])

    op.create_table(
        'underwriting_session_documents',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('session_id', sa.Text(), nullable=False),
        sa.Column('doc_type', sa.Text(), nullable=False),
        sa.Column('minio_key', sa.Text(), nullable=True),
        sa.Column('minio_url', sa.Text(), nullable=True),
        sa.Column('extracted_text', sa.Text(), nullable=True),
        sa.Column('validation_status', sa.Text(), nullable=True),
        sa.Column('uploaded_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()'), nullable=True),
        sa.Column('validated_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['session_id'], ['underwriting_sessions.session_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('session_id', 'doc_type', name='uq_underwriting_session_documents_session_doctype'),
    )
    op.create_index('ix_underwriting_session_documents_session', 'underwriting_session_documents', ['session_id'])

    op.create_table(
        'underwriting_pipeline_results',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('session_id', sa.Text(), nullable=False),
        sa.Column('flow_name', sa.Text(), nullable=False),
        sa.Column('status', sa.Text(), nullable=True),
        sa.Column('result_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('started_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()'), nullable=True),
        sa.Column('completed_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['session_id'], ['underwriting_sessions.session_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('session_id', 'flow_name', name='uq_underwriting_pipeline_results_session_flow'),
    )
    op.create_index('ix_underwriting_pipeline_results_session', 'underwriting_pipeline_results', ['session_id'])

    op.create_table(
        'underwriting_rules',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('category', sa.Text(), nullable=True),
        sa.Column('severity', sa.Text(), nullable=True, server_default=sa.text("'medium'")),
        sa.Column('condition', sa.Text(), nullable=True),
        sa.Column('threshold', sa.Text(), nullable=True),
        sa.Column('enabled', sa.Boolean(), nullable=True, server_default=sa.text('true')),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()'), nullable=True),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('NOW()'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    """Drop underwriting tables in reverse dependency order."""
    op.drop_table('underwriting_rules')
    op.drop_index('ix_underwriting_pipeline_results_session', table_name='underwriting_pipeline_results')
    op.drop_table('underwriting_pipeline_results')
    op.drop_index('ix_underwriting_session_documents_session', table_name='underwriting_session_documents')
    op.drop_table('underwriting_session_documents')
    op.drop_index('ix_underwriting_conversation_history_session', table_name='underwriting_conversation_history')
    op.drop_table('underwriting_conversation_history')
    op.drop_table('underwriting_sessions')
