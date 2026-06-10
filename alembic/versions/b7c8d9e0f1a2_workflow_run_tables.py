"""Add workflow run + run-step tables (WF-M1).

Makes a workflow runnable and auditable. ``workflow_run`` is one row per
execution (who triggered it, when, total duration, outcome); ``workflow_run_step``
is one row per node per execution (its input, output, status, attempt count, and
time taken). Full node payloads live in ``workflow_run_step`` — the record of
truth, redactable per pii_fields — and audit_log only references them.

Three enums:

  * workflow_run_status        queued | running | succeeded | failed | cancelled
  * workflow_actor_kind        user | cron | event | webhook_auth | webhook_anon
                               | fan_out_member
  * workflow_run_step_status   pending | running | succeeded | failed | skipped

``workflow_version_id`` / ``trigger_id`` are unconstrained UUID columns for now —
the version (M6) and trigger (M4) tables don't exist yet, so those slices add the
FK constraint, not the column.

Revision ID: b7c8d9e0f1a2
Revises: c1d2e3f4a5b6
Create Date: 2026-05-26
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, ENUM, JSONB, UUID


revision: str = "b7c8d9e0f1a2"
down_revision: Union[str, Sequence[str], None] = "c1d2e3f4a5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


workflow_run_status_enum = ENUM(
    "queued", "running", "succeeded", "failed", "cancelled",
    name="workflow_run_status", create_type=False,
)
workflow_actor_kind_enum = ENUM(
    "user", "cron", "event", "webhook_auth", "webhook_anon", "fan_out_member",
    name="workflow_actor_kind", create_type=False,
)
workflow_run_step_status_enum = ENUM(
    "pending", "running", "succeeded", "failed", "skipped",
    name="workflow_run_step_status", create_type=False,
)


def upgrade() -> None:
    workflow_run_status_enum.create(op.get_bind(), checkfirst=False)
    workflow_actor_kind_enum.create(op.get_bind(), checkfirst=False)
    workflow_run_step_status_enum.create(op.get_bind(), checkfirst=False)

    op.create_table(
        "workflow_run",
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
        # FK constraints added by M6 / M4 when those tables exist.
        sa.Column("workflow_version_id", UUID(as_uuid=False), nullable=True),
        sa.Column("trigger_id", UUID(as_uuid=False), nullable=True),
        sa.Column(
            "status", workflow_run_status_enum, nullable=False,
            server_default=sa.text("'queued'"),
        ),
        sa.Column(
            "actor_user_id", UUID(as_uuid=False),
            sa.ForeignKey("user.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("actor_kind", workflow_actor_kind_enum, nullable=False),
        sa.Column(
            "audit_principal_user_id", UUID(as_uuid=False),
            sa.ForeignKey("user.id", ondelete="RESTRICT"), nullable=False,
        ),
        sa.Column("temporal_run_id", sa.Text, nullable=True),
        sa.Column("trigger_payload", JSONB, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("finished_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_workflow_run_workflow_created", "workflow_run",
        ["workflow_id", "created_at"],
    )
    op.create_index(
        "ix_workflow_run_tenant_workspace", "workflow_run",
        ["tenant_id", "workspace_id"],
    )

    op.create_table(
        "workflow_run_step",
        sa.Column(
            "id", UUID(as_uuid=False), primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "run_id", UUID(as_uuid=False),
            sa.ForeignKey("workflow_run.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("step_id", sa.Text, nullable=False),
        sa.Column("node_kind", sa.Text, nullable=False),
        sa.Column(
            "status", workflow_run_step_status_enum, nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("input_json", JSONB, nullable=True),
        sa.Column("output_json", JSONB, nullable=True),
        sa.Column(
            "attempts", sa.Integer, nullable=False, server_default=sa.text("0"),
        ),
        sa.Column("pii_classification", ARRAY(sa.Text), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("finished_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_workflow_run_step_run", "workflow_run_step", ["run_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_workflow_run_step_run", table_name="workflow_run_step")
    op.drop_table("workflow_run_step")
    op.drop_index("ix_workflow_run_tenant_workspace", table_name="workflow_run")
    op.drop_index("ix_workflow_run_workflow_created", table_name="workflow_run")
    op.drop_table("workflow_run")
    sa.Enum(name="workflow_run_step_status").drop(op.get_bind(), checkfirst=False)
    sa.Enum(name="workflow_actor_kind").drop(op.get_bind(), checkfirst=False)
    sa.Enum(name="workflow_run_status").drop(op.get_bind(), checkfirst=False)
