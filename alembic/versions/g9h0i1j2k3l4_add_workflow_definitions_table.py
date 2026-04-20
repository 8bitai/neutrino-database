"""add ai_ops_workflow_definitions table

Revision ID: g9h0i1j2k3l4
Revises: f8a9b0c1d2e3
Create Date: 2026-03-23
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "g9h0i1j2k3l4"
down_revision = "f8a9b0c1d2e3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_ops_workflow_definitions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", UUID(as_uuid=False), sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("sop_id", UUID(as_uuid=True), sa.ForeignKey("ai_ops_sops.id", ondelete="SET NULL"), nullable=True),
        sa.Column("trigger_condition", sa.Text, nullable=True),
        sa.Column("activepieces_flow_name", sa.String(500), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default=sa.text("'active'")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_ai_ops_wf_defs_tenant", "ai_ops_workflow_definitions", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_ai_ops_wf_defs_tenant", table_name="ai_ops_workflow_definitions")
    op.drop_table("ai_ops_workflow_definitions")
