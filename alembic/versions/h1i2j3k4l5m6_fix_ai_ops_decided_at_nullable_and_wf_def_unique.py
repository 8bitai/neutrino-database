"""Fix ai_ops: make decided_at nullable, add unique constraint on workflow definition names.

Revision ID: h1i2j3k4l5m6
Revises: g9h0i1j2k3l4
Create Date: 2026-03-31

Changes:
- D2: Make ai_ops_approvals.decided_at nullable so "pending" approvals don't get
  a misleading timestamp. decided_at is now only set when decision becomes
  "approved" or "declined".
- D3: Add unique constraint uq_ai_ops_wf_defs_tenant_name on
  (tenant_id, name) in ai_ops_workflow_definitions to prevent ambiguous
  duplicate definition names per tenant.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "h1i2j3k4l5m6"
down_revision: Union[str, Sequence[str]] = "g9h0i1j2k3l4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # D2: Make decided_at nullable — pending approvals should not have a decided_at.
    # Must drop NOT NULL first, then clear stale values on pending rows.
    op.alter_column(
        "ai_ops_approvals",
        "decided_at",
        existing_type=sa.TIMESTAMP(timezone=True),
        nullable=True,
        server_default=None,
    )
    op.execute(
        "UPDATE ai_ops_approvals SET decided_at = NULL WHERE decision = 'pending'"
    )

    # D3: Add unique constraint on (tenant_id, name) for workflow definitions.
    op.create_unique_constraint(
        "uq_ai_ops_wf_defs_tenant_name",
        "ai_ops_workflow_definitions",
        ["tenant_id", "name"],
    )


def downgrade() -> None:
    # D3: Drop the unique constraint.
    op.drop_constraint(
        "uq_ai_ops_wf_defs_tenant_name",
        "ai_ops_workflow_definitions",
        type_="unique",
    )

    # D2: Restore decided_at as NOT NULL with server_default=now().
    # Back-fill NULLs before adding the NOT NULL constraint.
    op.execute(
        "UPDATE ai_ops_approvals SET decided_at = created_at WHERE decided_at IS NULL"
    )
    op.alter_column(
        "ai_ops_approvals",
        "decided_at",
        existing_type=sa.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )
