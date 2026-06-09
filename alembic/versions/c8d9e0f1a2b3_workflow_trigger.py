"""Add workflow_trigger table + link workflow_run.trigger_id (WF-M3a.2).

A stored trigger is how a workflow fires without a manual Run click. A webhook
trigger carries a unique ``token`` whose public URL (POST /triggers/{token})
starts a run with the request body as the trigger node's payload; cron/event
triggers carry their settings in ``config``. ``node_id`` binds the trigger to
the trigger node in the workflow's graph.

Two enums:
  * workflow_trigger_kind     webhook | cron | event
  * workflow_trigger_status   active | disabled

Also adds the FK constraint on ``workflow_run.trigger_id`` (the column already
exists, unconstrained, from WF-M1) → workflow_trigger, SET NULL on delete so a
deleted trigger keeps the run history, just unlinks it.

Revision ID: c8d9e0f1a2b3
Revises: b7c8d9e0f1a2
Create Date: 2026-05-27
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ENUM, JSONB, UUID


revision: str = "c8d9e0f1a2b3"
down_revision: Union[str, Sequence[str], None] = "b7c8d9e0f1a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


workflow_trigger_kind_enum = ENUM(
    "webhook", "cron", "event",
    name="workflow_trigger_kind", create_type=False,
)
workflow_trigger_status_enum = ENUM(
    "active", "disabled",
    name="workflow_trigger_status", create_type=False,
)


def upgrade() -> None:
    workflow_trigger_kind_enum.create(op.get_bind(), checkfirst=False)
    workflow_trigger_status_enum.create(op.get_bind(), checkfirst=False)

    op.create_table(
        "workflow_trigger",
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
        sa.Column(
            "workflow_id", UUID(as_uuid=False),
            sa.ForeignKey("workflow.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("node_id", sa.Text, nullable=False),
        sa.Column("kind", workflow_trigger_kind_enum, nullable=False),
        sa.Column("token", sa.Text, nullable=True),
        sa.Column(
            "config", JSONB, nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "status", workflow_trigger_status_enum, nullable=False,
            server_default=sa.text("'active'"),
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
            server_default=sa.func.now(), nullable=False,
        ),
    )
    op.create_index(
        "ix_workflow_trigger_workflow", "workflow_trigger", ["workflow_id"],
    )
    # Partial unique: O(1) webhook resolution; cron/event rows (token NULL) don't
    # collide on NULL.
    op.create_index(
        "uq_workflow_trigger_token", "workflow_trigger", ["token"],
        unique=True, postgresql_where=sa.text("token IS NOT NULL"),
    )

    # The trigger_id column landed in WF-M1 unconstrained; add its FK now.
    op.create_foreign_key(
        "fk_workflow_run_trigger_id", "workflow_run", "workflow_trigger",
        ["trigger_id"], ["id"], ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_workflow_run_trigger_id", "workflow_run", type_="foreignkey",
    )
    op.drop_index("uq_workflow_trigger_token", table_name="workflow_trigger")
    op.drop_index("ix_workflow_trigger_workflow", table_name="workflow_trigger")
    op.drop_table("workflow_trigger")
    workflow_trigger_status_enum.drop(op.get_bind(), checkfirst=False)
    workflow_trigger_kind_enum.drop(op.get_bind(), checkfirst=False)
