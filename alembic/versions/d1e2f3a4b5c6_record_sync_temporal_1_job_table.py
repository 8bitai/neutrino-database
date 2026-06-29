"""[NEU-1816] RECORD-SYNC-TEMPORAL-1 — integration_sync_job table.

Adds the top-level row that tracks one record-source sync run (Jira
project, Confluence space, ...) end-to-end. The Temporal workflow
heartbeats progress to this row; the FE / Indexed Content tab queries
it for run-level status, parallel to ``ingestion_jobs`` for the file
path.

Per-doc progress lives on the ``files`` row (processing_status), same
shape as file-source — so the existing Indexed Content polling already
shows record-source items as they index. This table is the run-level
roll-up so a 1,500-issue sync surfaces as a single row in the UI.

Columns:

  * id, tenant_id, workspace_id (resource scoping — same shape as the
    integration / file tables it joins to)
  * integration_id (FK → integration), container_id (per-provider unit
    id — Jira project key, Confluence space key, ...)
  * status enum (pending → running → succeeded | failed | cancelled)
  * temporal_workflow_id / temporal_run_id — handle for describe /
    cancel from the FE row
  * indexed_count, error_count, pages_completed — heartbeated by the
    workflow; the UI reads these for the progress label
  * last_heartbeat_at, started_at, completed_at — runtime observability
  * started_by, error_detail (NULL until status='failed')

Revision ID: d1e2f3a4b5c6
Revises: c9e0a1b2d3f4
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "d1e2f3a4b5c6"
down_revision: str | None = "c9e0a1b2d3f4"
branch_labels = None
depends_on = None


_STATUS_VALUES = ("pending", "running", "succeeded", "failed", "cancelled")


def upgrade() -> None:
    op.create_table(
        "integration_sync_job",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenant.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspace.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "integration_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("integration.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Per-provider unit id — Jira project key, Confluence space key.
        # Opaque to this table; the connector interprets it.
        sa.Column("container_id", sa.String(255), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                *_STATUS_VALUES,
                name="integration_sync_job_status",
            ),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        # Temporal handles. workflow_id is the deterministic key
        # (``sync:{job_id}`` — same shape as ``file:{file_id}``);
        # run_id is Temporal-assigned per attempt.
        sa.Column("temporal_workflow_id", sa.String(255), nullable=True),
        sa.Column("temporal_run_id", sa.String(255), nullable=True),
        # Progress heartbeated by the workflow. UI reads these for the
        # "1,234 indexed across 25 pages · 3 errors" label.
        sa.Column(
            "indexed_count",
            sa.Integer,
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "error_count",
            sa.Integer,
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "pages_completed",
            sa.Integer,
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "started_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user.id"),
            nullable=False,
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        # JSON because failure shapes vary — Jira API rate-limit, OpenFGA
        # tuple write failure, etc. Free-form for FE display.
        sa.Column(
            "error_detail",
            postgresql.JSONB,
            nullable=True,
        ),
    )

    # The "what's running right now?" lookup the FE polls.
    op.create_index(
        "ix_integration_sync_job_workspace_status",
        "integration_sync_job",
        ["workspace_id", "status"],
    )
    # Find the latest job per (integration, container) — used to show
    # "last synced N minutes ago" on the Content Sources card.
    op.create_index(
        "ix_integration_sync_job_integration_container_started",
        "integration_sync_job",
        ["integration_id", "container_id", sa.text("started_at DESC")],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_integration_sync_job_integration_container_started",
        table_name="integration_sync_job",
    )
    op.drop_index(
        "ix_integration_sync_job_workspace_status",
        table_name="integration_sync_job",
    )
    op.drop_table("integration_sync_job")
    op.execute("DROP TYPE IF EXISTS integration_sync_job_status")
