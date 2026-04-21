"""Add correlation_key to ai_ops_remedies for dedup.

Revision ID: k8l9m0n1p2q3
Revises: j7k8l9m0n1p2
Create Date: 2026-04-20 12:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "k8l9m0n1p2q3"
down_revision: Union[str, Sequence[str], None] = "j7k8l9m0n1p2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "ai_ops_remedies",
        sa.Column("correlation_key", sa.String(length=255), nullable=True),
    )
    op.create_index(
        "ux_ai_ops_remedies_tenant_corr_key",
        "ai_ops_remedies",
        ["tenant_id", "correlation_key"],
        unique=True,
        postgresql_where=sa.text("status = 'active' AND correlation_key IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "ux_ai_ops_remedies_tenant_corr_key",
        table_name="ai_ops_remedies",
    )
    op.drop_column("ai_ops_remedies", "correlation_key")
