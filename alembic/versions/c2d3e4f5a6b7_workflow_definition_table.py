"""Add workflow definition table (WF-VS2.1c).

The Workflow Execution pillar's workspace-scoped definition store: one row per
workflow the low-code builder produces. ``graph`` (JSONB) holds the node/edge
definition the GenericGraphWorkflow interprets; Temporal owns *execution* state
(event histories), this table owns the *definition*.

One enum:

  * workflow_status   draft | active | disabled | archived

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-05-20
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ENUM, JSONB, UUID


revision: str = "c2d3e4f5a6b7"
down_revision: Union[str, Sequence[str], None] = "b1c2d3e4f5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


workflow_status_enum = ENUM(
    "draft", "active", "disabled", "archived",
    name="workflow_status", create_type=False,
)


def upgrade() -> None:
    workflow_status_enum.create(op.get_bind(), checkfirst=False)

    op.create_table(
        "workflow",
        sa.Column(
            "id", UUID(as_uuid=False), primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "tenant_id", UUID(as_uuid=False),
            sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "workspace_id", UUID(as_uuid=False),
            sa.ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column(
            "graph", JSONB, nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "status", workflow_status_enum, nullable=False,
            server_default=sa.text("'draft'"),
        ),
        sa.Column(
            "created_by", UUID(as_uuid=False),
            sa.ForeignKey("user.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False,
        ),
    )
    op.create_index(
        "ix_workflow_tenant_workspace", "workflow",
        ["tenant_id", "workspace_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_workflow_tenant_workspace", table_name="workflow")
    op.drop_table("workflow")
    sa.Enum(name="workflow_status").drop(op.get_bind(), checkfirst=False)
