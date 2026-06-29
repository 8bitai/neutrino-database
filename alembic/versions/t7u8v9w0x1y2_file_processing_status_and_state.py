"""File processing status state machine + processing-state table.

Foundation schema for X-DOC-1 (Connector ↔ Ingestion refactor —
``user-stories/connect-ingestion-refactor.md``). Two pieces:

  1. **Typed file_processing_status state machine on ``files``.**

     Today ``files.status`` is a free-form ``String(50)`` written
     mostly with the server default ``'DOWNLOADED'``; no column
     captures *where the file is in its processing pipeline*. With
     X-DOC-1 we orchestrate file processing through Temporal, with
     each stage updating a typed status column users can observe
     in real time:

         pending -> fetching -> fetched
                    -> parsing -> chunking -> embedding
                    -> indexing -> acl_replicated -> indexed

         any -> failed   (terminal, with error_code + error_message)
         any -> deleted  (tombstone)
         failed -> fetching (retry)

     This adds ``files.processing_status`` (PgEnum), plus four
     companion columns:

         status_updated_at    when the row last transitioned
         error_code           machine-readable failure tag
         error_message        human-readable failure text
         error_retriable_at   when (or whether) auto-retry is due

     The existing ``files.status`` String column stays, deprecated;
     application code switches to ``processing_status`` over the
     X-DOC-1 phases. Tracked: TD-DOC-2 — drop ``status`` once no
     reader remains.

  2. **``file_processing_state`` table.**

     Per the X-DOC-1 design (decision 5.9), ingestion-as-pipeline
     gets a private retry/Temporal-state ledger keyed by file_id.
     The canonical user-visible state stays on the ``files`` row;
     this side table holds the retry counters, current Temporal
     workflow id, and stage-specific payloads that would otherwise
     pollute the canonical row.

     One row per file (``file_id`` is both PK and FK with
     ``ON DELETE CASCADE``). Created lazily — files don't get a row
     until ingestion picks them up.

Backfill choice
---------------
Existing rows get ``processing_status='indexed'`` if not soft-deleted,
``'deleted'`` if ``is_deleted = true``. Reasoning: production rows have
already moved through the legacy pipeline and are searchable today;
treating them as ``indexed`` lets X-DOC-1 land without re-processing
existing content. Soft-deleted rows get the tombstone state for
consistency with the new state machine.

Revision ID: t7u8v9w0x1y2
Revises: s6t7u8v9w0x1
Create Date: 2026-05-02 12:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "t7u8v9w0x1y2"
down_revision: Union[str, Sequence[str], None] = "s6t7u8v9w0x1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Enum lifecycle helpers — PgEnum types are global per database, so we
# create them explicitly and CASCADE-drop them on downgrade. Two-stage
# `create_type=False` on the column avoids the "type already exists"
# error if the migration is re-run after a partial failure.

FILE_PROCESSING_STATUS_NAME = "file_processing_status"

FILE_PROCESSING_STATUS_VALUES: tuple[str, ...] = (
    "pending",
    "fetching",
    "fetched",
    "parsing",
    "chunking",
    "embedding",
    "indexing",
    "acl_replicated",
    "indexed",
    "failed",
    "deleted",
)


def _file_processing_status_enum(create_type: bool = True) -> postgresql.ENUM:
    return postgresql.ENUM(
        *FILE_PROCESSING_STATUS_VALUES,
        name=FILE_PROCESSING_STATUS_NAME,
        create_type=create_type,
    )


def upgrade() -> None:
    bind = op.get_bind()

    # 1. Create the enum type explicitly so the same name is reused below.
    _file_processing_status_enum(create_type=True).create(bind, checkfirst=True)

    # 2. Add ``processing_status`` to files. Default 'pending' covers any
    #    row inserted between this migration landing and the backfill —
    #    realistically zero rows in any environment, but the default keeps
    #    NOT NULL safe.
    op.add_column(
        "files",
        sa.Column(
            "processing_status",
            _file_processing_status_enum(create_type=False),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
    )

    # 3. Backfill existing rows. Anything not soft-deleted is treated as
    #    fully processed (production rows have already cleared the legacy
    #    pipeline and are searchable). Soft-deleted rows get the tombstone
    #    state so the new state machine is internally consistent.
    op.execute(
        "UPDATE files "
        "   SET processing_status = CASE "
        "       WHEN is_deleted = true THEN 'deleted'::file_processing_status "
        "       ELSE 'indexed'::file_processing_status "
        "   END"
    )

    # 4. Companion columns — when did the row last transition, what failed
    #    (if anything), and when (if at all) is the next auto-retry due.
    op.add_column(
        "files",
        sa.Column(
            "status_updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.add_column(
        "files",
        sa.Column("error_code", sa.String(64), nullable=True),
    )
    op.add_column(
        "files",
        sa.Column("error_message", sa.Text(), nullable=True),
    )
    op.add_column(
        "files",
        sa.Column(
            "error_retriable_at",
            sa.TIMESTAMP(timezone=True),
            nullable=True,
        ),
    )

    # 5. Read-side index for the FE polling endpoint and the admin dashboard
    #    that filters by status. Per-workspace + status is the dominant
    #    filter shape ("show me failed files in this workspace").
    op.create_index(
        "ix_files_workspace_processing_status",
        "files",
        ["workspace_id", "processing_status"],
    )

    # 6. file_processing_state — the private side-table for ingestion's
    #    retry/Temporal state. PK = file_id, FK with ON DELETE CASCADE so
    #    tombstoning a file row also drops its processing state.
    op.create_table(
        "file_processing_state",
        sa.Column(
            "file_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("files.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "temporal_workflow_id",
            sa.String(255),
            nullable=True,
            comment="Temporal workflow id for the in-flight ingestion run; "
                    "shape: 'file:{uuid}'",
        ),
        sa.Column(
            "attempt_id",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
            comment="Increments on each retry of the full pipeline. "
                    "Used as part of the idempotency key for chunk / "
                    "embedding writes.",
        ),
        sa.Column(
            "last_activity",
            sa.String(64),
            nullable=True,
            comment="Name of the most recently observed activity, e.g. "
                    "'parse', 'chunk', 'embed', 'index', 'replicate_acl'.",
        ),
        sa.Column(
            "retry_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "next_retry_at",
            sa.TIMESTAMP(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "payload",
            postgresql.JSONB,
            nullable=True,
            comment="Activity-specific opaque state. Ingestion writes here; "
                    "documents-owner doesn't interpret.",
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )

    # Index for the retry-runner sweep (find files with next_retry_at <= now()).
    op.create_index(
        "ix_file_processing_state_due_retries",
        "file_processing_state",
        ["next_retry_at"],
        postgresql_where=sa.text("next_retry_at IS NOT NULL"),
    )


def downgrade() -> None:
    # Reverse order — drop indexes + table first, then drop columns, then
    # the enum type itself (which can only go away once nothing references
    # it).
    op.drop_index(
        "ix_file_processing_state_due_retries",
        table_name="file_processing_state",
    )
    op.drop_table("file_processing_state")

    op.drop_index(
        "ix_files_workspace_processing_status",
        table_name="files",
    )
    op.drop_column("files", "error_retriable_at")
    op.drop_column("files", "error_message")
    op.drop_column("files", "error_code")
    op.drop_column("files", "status_updated_at")
    op.drop_column("files", "processing_status")

    bind = op.get_bind()
    _file_processing_status_enum(create_type=False).drop(bind, checkfirst=True)
