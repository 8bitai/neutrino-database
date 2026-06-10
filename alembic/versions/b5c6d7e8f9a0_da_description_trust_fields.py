"""DA description trust fields + workspace_da_settings (DA-P1l.1.0).

Collapses the two-field description model on both curation tables into a
single ``description`` field with trust metadata. Drops the per-column
``allow_sample_values`` toggle (lifted to workspace-level). Creates the
``workspace_da_settings`` table.

Locked design: ``product-feature-roadmap/data-analytics/description-generation.md``
decisions M1, M2, M11.

Why one migration covers all four changes:

  * The schema reshape is one logical product call (single-field model
    + trust metadata + workspace-level toggles). Splitting it would let
    code land between migrations with an inconsistent description
    model — same trap that motivated F4.
  * Per-table ``allow_sample_values`` is being replaced by
    ``workspace_da_settings.da_include_sample_values`` in the same
    breath; doing them together avoids leaving the column dangling in
    one migration and the workspace setting absent in another.

Changes per table
-----------------

workspace_curation_da_table:

  * RENAME COLUMN admin_seed_description → description.
  * Backfill any rows where ai_generated_description is set but
    admin_seed (now ``description``) is empty — copy AI text into
    description, set origin='ai'. Preserves data even though current
    production likely has no rows with this shape.
  * ADD COLUMN description_origin VARCHAR(8) NOT NULL DEFAULT 'human'
    + CHECK constraint (human | ai).
  * ADD COLUMN ai_accepted_at TIMESTAMPTZ NULL.
  * ADD COLUMN ai_last_generated_at TIMESTAMPTZ NULL.
  * DROP COLUMN ai_generated_description.

workspace_curation_da_column:

  * Same column changes as the table.
  * DROP COLUMN allow_sample_values (lifted to workspace-level per M11).

workspace_da_settings (new):

  * workspace_id UUID PK + FK → workspace(id) ON DELETE CASCADE.
  * da_include_sample_values BOOLEAN NOT NULL DEFAULT true.
  * da_pii_redaction_enabled BOOLEAN NOT NULL DEFAULT true.
  * created_at / updated_at TIMESTAMPTZ.

Both new toggles default TRUE (fail-safe). Row is lazy-created on first
PATCH; absence means defaults apply.

Revision ID: b5c6d7e8f9a0
Revises: a4b5c6d7e8f9
Create Date: 2026-05-12
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PG_UUID


revision: str = "b5c6d7e8f9a0"
down_revision: Union[str, Sequence[str], None] = "a4b5c6d7e8f9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ---------------------------------------------------------------------------
# Helpers — same migration shape applied to both curation tables.
# ---------------------------------------------------------------------------

_CURATION_TABLES = (
    ("workspace_curation_da_table", "ck_wcdt_description_origin"),
    ("workspace_curation_da_column", "ck_wcdc_description_origin"),
)


def _upgrade_curation_table(table_name: str, check_name: str) -> None:
    """Apply the description-collapse + trust-fields shape change to one
    curation table. Order matters:
      1. Rename admin_seed → description so the new field exists.
      2. Add trust columns (origin defaults to 'human').
      3. Backfill: rows that had only AI text become origin='ai' with
         the AI text moved into ``description``.
      4. Drop ai_generated_description.
      5. Attach CHECK constraint after data is normalized.
    """
    # 1. Rename existing admin column to the canonical name.
    op.alter_column(
        table_name,
        "admin_seed_description",
        new_column_name="description",
    )

    # 2. Add trust metadata columns. origin NOT NULL DEFAULT 'human'.
    op.add_column(
        table_name,
        sa.Column(
            "description_origin",
            sa.String(length=8),
            nullable=False,
            server_default=sa.text("'human'"),
        ),
    )
    op.add_column(
        table_name,
        sa.Column(
            "ai_accepted_at",
            sa.TIMESTAMP(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        table_name,
        sa.Column(
            "ai_last_generated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=True,
        ),
    )

    # 3. Defensive backfill: preserve any AI-generated text that
    #    populated ai_generated_description but never reached description.
    #    Current production likely has no such rows (description gen
    #    isn't shipped yet) but the migration must be data-safe.
    op.execute(
        f"""
        UPDATE {table_name}
           SET description = ai_generated_description,
               description_origin = 'ai',
               ai_last_generated_at = updated_at
         WHERE ai_generated_description IS NOT NULL
           AND description IS NULL
        """
    )

    # 4. Drop the now-redundant AI column.
    op.drop_column(table_name, "ai_generated_description")

    # 5. CHECK constraint applied after backfill so any out-of-band
    #    'ai' rows we just wrote pass the constraint.
    op.create_check_constraint(
        check_name,
        table_name,
        "description_origin IN ('human', 'ai')",
    )


def _downgrade_curation_table(table_name: str, check_name: str) -> None:
    """Revert the curation table to the two-field model.

    Lossy: ai_accepted_at and ai_last_generated_at info is dropped;
    description_origin distinction is collapsed back into two parallel
    columns where AI text goes into ai_generated_description.
    """
    op.drop_constraint(check_name, table_name, type_="check")

    # Re-add the AI column.
    op.add_column(
        table_name,
        sa.Column("ai_generated_description", sa.Text(), nullable=True),
    )

    # Move ai-origin descriptions back to the AI column; clear
    # description for those rows so admin_seed semantics are preserved.
    op.execute(
        f"""
        UPDATE {table_name}
           SET ai_generated_description = description,
               description = NULL
         WHERE description_origin = 'ai'
        """
    )

    op.drop_column(table_name, "ai_last_generated_at")
    op.drop_column(table_name, "ai_accepted_at")
    op.drop_column(table_name, "description_origin")

    op.alter_column(
        table_name,
        "description",
        new_column_name="admin_seed_description",
    )


# ---------------------------------------------------------------------------
# Migration entrypoints
# ---------------------------------------------------------------------------


def upgrade() -> None:
    # Both curation tables get the same reshape.
    for table_name, check_name in _CURATION_TABLES:
        _upgrade_curation_table(table_name, check_name)

    # workspace_curation_da_column also loses the per-column sampling
    # toggle (M11 — lifted to workspace-level).
    op.drop_column("workspace_curation_da_column", "allow_sample_values")

    # New workspace_da_settings table (M11).
    op.create_table(
        "workspace_da_settings",
        sa.Column(
            "workspace_id",
            PG_UUID(as_uuid=False),
            sa.ForeignKey("workspace.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "da_include_sample_values",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "da_pii_redaction_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
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
            nullable=False,
        ),
    )


def downgrade() -> None:
    # Reverse order of upgrade.
    op.drop_table("workspace_da_settings")

    # Re-add allow_sample_values with the post-a4b5c6d7e8f9 default
    # (true). Pre-migration value cannot be recovered; this matches
    # what the previous migration set.
    op.add_column(
        "workspace_curation_da_column",
        sa.Column(
            "allow_sample_values",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )

    # Reverse curation reshape in reverse table order so any FK / shape
    # symmetry is preserved.
    for table_name, check_name in reversed(_CURATION_TABLES):
        _downgrade_curation_table(table_name, check_name)
