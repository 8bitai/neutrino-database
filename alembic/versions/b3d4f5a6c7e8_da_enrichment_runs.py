"""NC-103 — da_enrichment_run + da_enrichment_table_item.

Durable DA catalog enrichment: the Data Curation page's Reprofile /
Regenerate buttons stop being a client-side sequential loop with a
local "busy" flag (lost on refresh) and instead start a Temporal run
whose progress is projected into these two tables. The page polls the
projection and re-attaches to any in-flight run after a refresh.

  * ``da_enrichment_run``        — one row per triggered run: the command
    record (scope × operation × target), the Temporal handle, and rollup
    counters for the header progress bar.
  * ``da_enrichment_table_item`` — per-table, two-stage progress
    (``profile_status`` / ``describe_status`` advance independently;
    NULL = stage not part of this run's operation).

Four enums:
  * ``da_enrichment_scope``        connection | schema | table
  * ``da_enrichment_operation``    profile | describe | enrich
  * ``da_enrichment_run_status``   pending | running | completed |
                                   completed_with_errors | failed | cancelled
  * ``da_enrichment_stage_status`` pending | running | done | skipped | failed

The DA connection is an ``integration`` row (unified integration model),
mirroring ``da_catalog_schema.da_connection_id``. Pre-production: no rows
to backfill.

Revision ID: b3d4f5a6c7e8
Revises: f1a2b3c4d5e6
Create Date: 2026-06-18
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ENUM, UUID


revision: str = "b3d4f5a6c7e8"
down_revision: Union[str, Sequence[str], None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# One enum object per type, shared between explicit .create() and the column
# reference so SQLAlchemy doesn't auto-create on column bind. The stage-status
# enum is referenced by two columns (profile_status / describe_status) — one
# object, created once.
scope_enum = ENUM(
    "connection", "schema", "table",
    name="da_enrichment_scope",
    create_type=False,
)
operation_enum = ENUM(
    "profile", "describe", "enrich",
    name="da_enrichment_operation",
    create_type=False,
)
run_status_enum = ENUM(
    "pending", "running", "completed", "completed_with_errors", "failed", "cancelled",
    name="da_enrichment_run_status",
    create_type=False,
)
stage_status_enum = ENUM(
    "pending", "running", "done", "skipped", "failed",
    name="da_enrichment_stage_status",
    create_type=False,
)


def upgrade() -> None:
    scope_enum.create(op.get_bind(), checkfirst=False)
    operation_enum.create(op.get_bind(), checkfirst=False)
    run_status_enum.create(op.get_bind(), checkfirst=False)
    stage_status_enum.create(op.get_bind(), checkfirst=False)

    op.create_table(
        "da_enrichment_run",
        sa.Column(
            "id",
            UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "tenant_id",
            UUID(as_uuid=False),
            sa.ForeignKey("tenant.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "workspace_id",
            UUID(as_uuid=False),
            sa.ForeignKey("workspace.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "connection_id",
            UUID(as_uuid=False),
            sa.ForeignKey("integration.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("scope", scope_enum, nullable=False),
        sa.Column("operation", operation_enum, nullable=False),
        sa.Column(
            "schema_id",
            UUID(as_uuid=False),
            sa.ForeignKey("da_catalog_schema.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "table_id",
            UUID(as_uuid=False),
            sa.ForeignKey("da_catalog_table.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "status", run_status_enum, nullable=False, server_default=sa.text("'pending'")
        ),
        sa.Column("total_tables", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("completed_tables", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("failed_tables", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("skipped_tables", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("temporal_workflow_id", sa.Text(), nullable=True),
        sa.Column("temporal_run_id", sa.Text(), nullable=True),
        sa.Column(
            "created_by_user_id",
            UUID(as_uuid=False),
            sa.ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("finished_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_da_enrichment_run_workspace_status",
        "da_enrichment_run",
        ["workspace_id", "status"],
    )
    op.create_index(
        "ix_da_enrichment_run_connection_status",
        "da_enrichment_run",
        ["connection_id", "status"],
    )

    op.create_table(
        "da_enrichment_table_item",
        sa.Column(
            "id",
            UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "run_id",
            UUID(as_uuid=False),
            sa.ForeignKey("da_enrichment_run.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "da_catalog_table_id",
            UUID(as_uuid=False),
            sa.ForeignKey("da_catalog_table.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("schema_name", sa.String(length=255), nullable=False),
        sa.Column("table_name", sa.String(length=255), nullable=False),
        sa.Column("profile_status", stage_status_enum, nullable=True),
        sa.Column("describe_status", stage_status_enum, nullable=True),
        sa.Column("columns_total", sa.Integer(), nullable=True),
        sa.Column(
            "columns_described", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("finished_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "run_id", "da_catalog_table_id",
            name="uq_da_enrichment_table_item_run_table",
        ),
    )
    op.create_index(
        "ix_da_enrichment_table_item_run",
        "da_enrichment_table_item",
        ["run_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_da_enrichment_table_item_run", table_name="da_enrichment_table_item")
    op.drop_table("da_enrichment_table_item")
    op.drop_index("ix_da_enrichment_run_connection_status", table_name="da_enrichment_run")
    op.drop_index("ix_da_enrichment_run_workspace_status", table_name="da_enrichment_run")
    op.drop_table("da_enrichment_run")
    sa.Enum(name="da_enrichment_stage_status").drop(op.get_bind(), checkfirst=False)
    sa.Enum(name="da_enrichment_run_status").drop(op.get_bind(), checkfirst=False)
    sa.Enum(name="da_enrichment_operation").drop(op.get_bind(), checkfirst=False)
    sa.Enum(name="da_enrichment_scope").drop(op.get_bind(), checkfirst=False)
