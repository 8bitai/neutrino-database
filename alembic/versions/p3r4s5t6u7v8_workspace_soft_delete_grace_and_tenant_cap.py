"""Workspace soft-delete-with-grace + per-tenant workspace cap.

Adds the schema NEU-1805 phase 5 needs to ship production-grade
workspace deletion:

  1. ``workspace.deletion_scheduled_for`` (TIMESTAMPTZ NULL)
       Stamped at soft-delete time as ``deleted_at + 30 days``. The
       retention runner uses this exact value to decide when to
       physically remove the row. Storing it explicitly (rather than
       computing it from ``deleted_at + grace constant``) means a
       future change to the grace-period default doesn't silently
       shift existing pending deletions.

  2. ``workspace.deletion_initiated_by`` (UUID NULL, FK user(id) ON DELETE SET NULL)
       Audit-correlatable: who clicked Delete. SET NULL on user
       deletion so a user can be anonymized (GDPR Art. 17) without
       breaking workspace deletion history.

  3. ``tenant.max_workspaces`` (INTEGER NOT NULL DEFAULT 50)
       Per-tenant cap on active workspaces. Soft-deleted workspaces
       don't count toward this cap (they're heading out via the
       retention runner). Enterprise customers have their cap
       raised via a one-row UPDATE instead of a code change.

  4. **Partial unique index** ``ux_workspace_tenant_name_active``
       Replaces the previous full ``UniqueConstraint("tenant_id",
       "name")``. Soft-deleted workspaces no longer block a new
       workspace with the same name during the 30-day grace period.
       Without this fix, deleting "Engineering" would make the name
       unavailable for 30 days even though the deletion may yet be
       reversed — a real UX bug surfaced by the soft-delete shape.

  5. **Pending-deletion read index** ``ix_workspace_pending_deletion``
       Partial index over ``deletion_scheduled_for`` filtered by
       ``deleted_at IS NOT NULL AND deletion_scheduled_for IS NOT NULL``.
       The hard-delete runner sweeps with
       ``WHERE deletion_scheduled_for < now()`` daily; this index
       keeps that sweep cheap.

See ``user-stories/tenant-admin-actions.md`` § 1c (soft-delete with
grace), § 1d (per-tenant cap), and § 1e (retention runner) for the
product-level decisions.

Revision ID: p3r4s5t6u7v8
Revises: o2q3r4s5t6u7
Create Date: 2026-04-29 14:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "p3r4s5t6u7v8"
down_revision: Union[str, Sequence[str], None] = "o2q3r4s5t6u7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. workspace.deletion_scheduled_for
    op.add_column(
        "workspace",
        sa.Column("deletion_scheduled_for", sa.TIMESTAMP(timezone=True), nullable=True),
    )

    # 2. workspace.deletion_initiated_by + FK
    op.add_column(
        "workspace",
        sa.Column("deletion_initiated_by", sa.dialects.postgresql.UUID(as_uuid=False), nullable=True),
    )
    op.create_foreign_key(
        "workspace_deletion_initiated_by_fkey",
        source_table="workspace",
        referent_table="user",
        local_cols=["deletion_initiated_by"],
        remote_cols=["id"],
        ondelete="SET NULL",
    )

    # 3. tenant.max_workspaces with default 50
    # Add as nullable first, backfill, then set NOT NULL — protects any
    # existing tenant rows that pre-date this column. The server_default
    # covers future inserts.
    op.add_column(
        "tenant",
        sa.Column(
            "max_workspaces",
            sa.Integer(),
            nullable=True,
            server_default=sa.text("50"),
        ),
    )
    op.execute("UPDATE tenant SET max_workspaces = 50 WHERE max_workspaces IS NULL")
    op.alter_column("tenant", "max_workspaces", nullable=False)

    # 4. Partial unique index on workspace(tenant_id, name) WHERE deleted_at IS NULL
    # Drop the old full constraint first so the predicate-version
    # supersedes it without overlap.
    op.drop_constraint(
        "ux_workspace_tenant_name",
        "workspace",
        type_="unique",
    )
    op.create_index(
        "ux_workspace_tenant_name_active",
        "workspace",
        ["tenant_id", "name"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    # 5. Partial read index for the retention runner sweep
    op.create_index(
        "ix_workspace_pending_deletion",
        "workspace",
        ["deletion_scheduled_for"],
        postgresql_where=sa.text(
            "deleted_at IS NOT NULL AND deletion_scheduled_for IS NOT NULL"
        ),
    )


def downgrade() -> None:
    # Reverse order of upgrade() — drop indexes first, restore the old
    # full unique constraint, then drop columns.
    op.drop_index("ix_workspace_pending_deletion", table_name="workspace")
    op.drop_index("ux_workspace_tenant_name_active", table_name="workspace")
    op.create_unique_constraint(
        "ux_workspace_tenant_name",
        "workspace",
        ["tenant_id", "name"],
    )
    op.drop_column("tenant", "max_workspaces")
    op.drop_constraint(
        "workspace_deletion_initiated_by_fkey",
        "workspace",
        type_="foreignkey",
    )
    op.drop_column("workspace", "deletion_initiated_by")
    op.drop_column("workspace", "deletion_scheduled_for")
