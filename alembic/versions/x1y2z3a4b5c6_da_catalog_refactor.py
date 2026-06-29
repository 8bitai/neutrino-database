"""DA metadata refactor — tenant catalog + workspace overlay split (NEU-1811 DA-P1g).

The original DA-P0 design baked workspace ownership into every metadata
row (``workspace_metadata_connection / table / column``). Two production-
grade problems emerged once the design conversation ran longer:

  1. **Wasted work + drift.** N workspaces using the same warehouse
     re-crawl it N times, store N copies of the catalog, and drift apart
     when columns change. Mature catalog systems (Looker, dbt, Hex,
     Metabase) discover the schema **once per source** and layer
     workspace-level curation on top.
  2. **PII compliance landmine.** ``is_pii`` lived per-workspace. Same
     ``ssn`` column tagged PII by workspace A and not-PII by workspace
     B is a SOC2 / HIPAA / GDPR violation: the same physical data is
     classified inconsistently across audit logs and exports.

This migration locks in the "facts up, opinions down" pattern:

  * Tenant level — facts:
      ``da_catalog_schema`` → ``da_catalog_table`` → ``da_catalog_column``
      Holds discovered DDL + native comments + PII / restricted
      classification. Shared across every workspace in the tenant.
      Re-synced as a single pass per re-crawl.

  * Workspace level — opinions / curation overlays:
      ``workspace_curation_da_table`` (workspace, da_catalog_table_id)
      ``workspace_curation_da_column`` (workspace, da_catalog_column_id)
      Thin overlays: is_included / archived, admin seed descriptions,
      AI-generated descriptions (per workspace — different teams describe
      the same column differently), synonyms / units / sample values /
      valid aggregations, ``is_restricted_override`` (upgrade-only —
      a workspace can ADD restriction but never disagree with the
      catalog's PII).

The same pattern locks in for ES when ES Connections migrate to tenant
level (catalog tables + workspace curation overlays in the same shape).

What this migration does (data-safe — all workspace_metadata_* tables
are zero-rows at this point):

  1. Drop the FK constraints on ``join_hint`` that reference
     ``workspace_metadata_table`` so we can drop those tables.
  2. Drop ``workspace_metadata_column``, ``workspace_metadata_table``,
     ``workspace_metadata_connection`` (in FK order).
  3. Create the three ``da_catalog_*`` tables (tenant facts).
  4. Create the two ``workspace_curation_da_*`` overlays.
  5. Re-add ``join_hint`` FK constraints to
     ``workspace_curation_da_table`` (joins are workspace-scoped
     opinions about useful joins; they reference the workspace's curated
     subset, not the tenant catalog).

PII tagging (per ``our-engineering-standards.md`` §13) preserved:
  * ``da_connection.credentials``                           pii:credentials  (untouched)
  * ``workspace_curation_da_column.sample_values``          pii:freetext      (re-applied)
  * ``description_version.inputs_snapshot``                 pii:freetext      (untouched)

Revision ID: x1y2z3a4b5c6
Revises: w0x1y2z3a4b5
Create Date: 2026-05-11 22:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "x1y2z3a4b5c6"
down_revision: Union[str, Sequence[str], None] = "w0x1y2z3a4b5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ----------------------------------------------------------------
    # Step 1 — sever join_hint's references to the old metadata tables
    # so we can drop them.
    # ----------------------------------------------------------------
    op.drop_constraint(
        "join_hint_left_table_id_fkey", "join_hint", type_="foreignkey"
    )
    op.drop_constraint(
        "join_hint_right_table_id_fkey", "join_hint", type_="foreignkey"
    )

    # ----------------------------------------------------------------
    # Step 2 — drop the old workspace_metadata_* tables in FK order.
    # All are zero-rows at this point (DA-P0 just shipped; no curation
    # has happened yet), so this is a clean drop.
    # ----------------------------------------------------------------
    op.drop_table("workspace_metadata_column")
    op.drop_table("workspace_metadata_table")
    op.drop_table("workspace_metadata_connection")

    # ----------------------------------------------------------------
    # Step 3 — tenant catalog: da_catalog_schema / table / column
    # ----------------------------------------------------------------
    op.create_table(
        "da_catalog_schema",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "da_connection_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("da_connection.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("schema_name", sa.String(length=255), nullable=False),
        sa.Column("schema_description", sa.Text(), nullable=True),
        sa.Column("last_synced_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ux_da_catalog_schema_conn_name",
        "da_catalog_schema",
        ["da_connection_id", "schema_name"],
        unique=True,
    )
    op.create_index(
        "ix_da_catalog_schema_conn",
        "da_catalog_schema",
        ["da_connection_id"],
    )

    op.create_table(
        "da_catalog_table",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "da_catalog_schema_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("da_catalog_schema.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("table_name", sa.String(length=255), nullable=False),
        sa.Column(
            "table_type",
            postgresql.ENUM(name="da_table_type", create_type=False),
            nullable=False,
            server_default=sa.text("'table'"),
        ),
        sa.Column("native_comment", sa.Text(), nullable=True),
        sa.Column("row_count", sa.BigInteger(), nullable=True),
        sa.Column("last_synced_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ux_da_catalog_table_schema_name",
        "da_catalog_table",
        ["da_catalog_schema_id", "table_name"],
        unique=True,
    )
    op.create_index(
        "ix_da_catalog_table_schema",
        "da_catalog_table",
        ["da_catalog_schema_id"],
    )

    op.create_table(
        "da_catalog_column",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "da_catalog_table_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("da_catalog_table.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # DDL-derived facts
        sa.Column("column_name", sa.String(length=255), nullable=False),
        sa.Column("data_type", sa.String(length=255), nullable=False),
        sa.Column("nullable", sa.Boolean(), nullable=False),
        sa.Column(
            "is_primary_key",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "is_foreign_key",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "foreign_key_to",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("native_comment", sa.Text(), nullable=True),
        sa.Column("ordinal_position", sa.Integer(), nullable=False),
        # Compliance classification — tenant-owned. Workspace cannot
        # disagree (PII has no override; restricted can only be
        # upgraded via workspace_curation_da_column.is_restricted_override).
        sa.Column(
            "is_pii",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "is_restricted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        # Lifecycle
        sa.Column("last_synced_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ux_da_catalog_column_table_name",
        "da_catalog_column",
        ["da_catalog_table_id", "column_name"],
        unique=True,
    )
    op.create_index(
        "ix_da_catalog_column_table",
        "da_catalog_column",
        ["da_catalog_table_id"],
    )

    # ----------------------------------------------------------------
    # Step 4 — workspace curation overlays (thin opinion rows)
    # ----------------------------------------------------------------
    op.create_table(
        "workspace_curation_da_table",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("workspace.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "da_catalog_table_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("da_catalog_table.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Per-workspace opinion / context
        sa.Column("table_logical_name", sa.String(length=255), nullable=True),
        sa.Column("admin_seed_description", sa.Text(), nullable=True),
        sa.Column("ai_generated_description", sa.Text(), nullable=True),
        # Curation
        sa.Column(
            "is_included",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "is_archived",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("last_enriched_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ux_wcdt_workspace_catalog",
        "workspace_curation_da_table",
        ["workspace_id", "da_catalog_table_id"],
        unique=True,
    )
    op.create_index(
        "ix_wcdt_workspace",
        "workspace_curation_da_table",
        ["workspace_id"],
    )
    op.create_index(
        "ix_wcdt_catalog",
        "workspace_curation_da_table",
        ["da_catalog_table_id"],
    )

    op.create_table(
        "workspace_curation_da_column",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("workspace.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "da_catalog_column_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("da_catalog_column.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Per-workspace LLM context — the AI describes the same column
        # differently for different teams (sales workspace ≠ finance
        # workspace), so this lives per-workspace, not on the catalog.
        sa.Column("column_logical_name", sa.String(length=255), nullable=True),
        sa.Column("admin_seed_description", sa.Text(), nullable=True),
        sa.Column("ai_generated_description", sa.Text(), nullable=True),
        sa.Column(
            "synonyms",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("unit", sa.String(length=64), nullable=True),
        sa.Column("format_hint", sa.String(length=64), nullable=True),
        sa.Column(
            "valid_aggregations",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "allow_sample_values",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "sample_values",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="pii:freetext",
        ),
        sa.Column("cardinality_score", sa.Float(), nullable=True),
        sa.Column(
            "statistical_profile",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        # Upgrade-only restricted override. A workspace can ADD
        # restriction on top of the catalog's is_restricted, but app
        # code never lets it DISAGREE with the catalog's classification.
        # The catalog's is_pii has no override at all — strictly
        # tenant-owned.
        sa.Column(
            "is_restricted_override",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        # Curation
        sa.Column(
            "is_included",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "is_archived",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("last_enriched_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ux_wcdc_workspace_catalog",
        "workspace_curation_da_column",
        ["workspace_id", "da_catalog_column_id"],
        unique=True,
    )
    op.create_index(
        "ix_wcdc_workspace",
        "workspace_curation_da_column",
        ["workspace_id"],
    )
    op.create_index(
        "ix_wcdc_catalog",
        "workspace_curation_da_column",
        ["da_catalog_column_id"],
    )

    # ----------------------------------------------------------------
    # Step 5 — repoint join_hint FKs to workspace_curation_da_table.
    # Join hints are workspace opinions ("these two tables join usefully
    # for us") — they reference the workspace's curated subset, not the
    # tenant catalog.
    # ----------------------------------------------------------------
    op.create_foreign_key(
        "join_hint_left_table_id_fkey",
        "join_hint",
        "workspace_curation_da_table",
        ["left_table_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "join_hint_right_table_id_fkey",
        "join_hint",
        "workspace_curation_da_table",
        ["right_table_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    # Reverse step 5
    op.drop_constraint(
        "join_hint_right_table_id_fkey", "join_hint", type_="foreignkey"
    )
    op.drop_constraint(
        "join_hint_left_table_id_fkey", "join_hint", type_="foreignkey"
    )

    # Reverse step 4
    op.drop_table("workspace_curation_da_column")
    op.drop_table("workspace_curation_da_table")

    # Reverse step 3
    op.drop_table("da_catalog_column")
    op.drop_table("da_catalog_table")
    op.drop_table("da_catalog_schema")

    # Reverse step 2 — recreate the workspace_metadata_* tables in the
    # original shape so a clean revert lands in DA-P0 baseline state.
    op.create_table(
        "workspace_metadata_connection",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("workspace.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "connection_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("da_connection.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "source_type",
            postgresql.ENUM(name="da_source_type", create_type=False),
            nullable=False,
        ),
        sa.Column("connection_name", sa.String(length=255), nullable=False),
        sa.Column("database_name", sa.String(length=255), nullable=False),
        sa.Column("schema_name", sa.String(length=255), nullable=False),
        sa.Column("schema_description", sa.Text(), nullable=True),
        sa.Column("last_synced_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ux_wmc_workspace_conn_db_schema",
        "workspace_metadata_connection",
        ["workspace_id", "connection_id", "database_name", "schema_name"],
        unique=True,
    )
    op.create_index(
        "ix_wmc_workspace",
        "workspace_metadata_connection",
        ["workspace_id"],
    )

    op.create_table(
        "workspace_metadata_table",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "workspace_metadata_connection_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey(
                "workspace_metadata_connection.id", ondelete="CASCADE"
            ),
            nullable=False,
        ),
        sa.Column("table_name", sa.String(length=255), nullable=False),
        sa.Column(
            "table_type",
            postgresql.ENUM(name="da_table_type", create_type=False),
            nullable=False,
            server_default=sa.text("'table'"),
        ),
        sa.Column("native_comment", sa.Text(), nullable=True),
        sa.Column("row_count", sa.BigInteger(), nullable=True),
        sa.Column("table_logical_name", sa.String(length=255), nullable=True),
        sa.Column("admin_seed_description", sa.Text(), nullable=True),
        sa.Column("ai_generated_description", sa.Text(), nullable=True),
        sa.Column(
            "is_included",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "is_archived",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("last_enriched_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ux_wmt_connection_table_name",
        "workspace_metadata_table",
        ["workspace_metadata_connection_id", "table_name"],
        unique=True,
    )
    op.create_index(
        "ix_wmt_connection",
        "workspace_metadata_table",
        ["workspace_metadata_connection_id"],
    )

    op.create_table(
        "workspace_metadata_column",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "workspace_metadata_table_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey(
                "workspace_metadata_table.id", ondelete="CASCADE"
            ),
            nullable=False,
        ),
        sa.Column("column_name", sa.String(length=255), nullable=False),
        sa.Column("data_type", sa.String(length=255), nullable=False),
        sa.Column("nullable", sa.Boolean(), nullable=False),
        sa.Column(
            "is_primary_key",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "is_foreign_key",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "foreign_key_to",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("native_comment", sa.Text(), nullable=True),
        sa.Column("ordinal_position", sa.Integer(), nullable=False),
        sa.Column("column_logical_name", sa.String(length=255), nullable=True),
        sa.Column("admin_seed_description", sa.Text(), nullable=True),
        sa.Column("ai_generated_description", sa.Text(), nullable=True),
        sa.Column(
            "is_pii",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "is_restricted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "allow_sample_values",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "sample_values",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="pii:freetext",
        ),
        sa.Column("cardinality_score", sa.Float(), nullable=True),
        sa.Column(
            "statistical_profile",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "synonyms",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("unit", sa.String(length=64), nullable=True),
        sa.Column("format_hint", sa.String(length=64), nullable=True),
        sa.Column(
            "valid_aggregations",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "is_included",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "is_archived",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("last_enriched_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ux_wmcol_table_column_name",
        "workspace_metadata_column",
        ["workspace_metadata_table_id", "column_name"],
        unique=True,
    )
    op.create_index(
        "ix_wmcol_table",
        "workspace_metadata_column",
        ["workspace_metadata_table_id"],
    )

    # Reverse step 1 — restore join_hint FKs to workspace_metadata_table.
    op.create_foreign_key(
        "join_hint_left_table_id_fkey",
        "join_hint",
        "workspace_metadata_table",
        ["left_table_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "join_hint_right_table_id_fkey",
        "join_hint",
        "workspace_metadata_table",
        ["right_table_id"],
        ["id"],
        ondelete="CASCADE",
    )
