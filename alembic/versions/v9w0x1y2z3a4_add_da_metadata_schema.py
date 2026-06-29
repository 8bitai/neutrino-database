"""Add the DA metadata schema — 7 tables + 8 enum types (NEU-1811 DA-P0).

The Data Analytics pillar's per-warehouse curated state. See spec at
``product-feature-roadmap/data-analytics/data-flow.md`` §4.8.

Tables created:

  * ``da_connection`` — tenant-level Connection. Holds credentials (PII)
    + lifecycle status. Connector-service owns CRUD (feature.md F4).
  * ``workspace_metadata_connection`` — one row per
    (workspace_id, connection_id, database_name, schema_name).
  * ``workspace_metadata_table`` — DDL + curation + descriptions per
    table within a curated schema.
  * ``workspace_metadata_column`` — DDL + descriptions + privacy flags
    + Phase-2 enrichments (samples / cardinality / stats) + semantic
    fields (synonyms / unit / format_hint / valid_aggregations).
  * ``metric`` — workspace-scoped business metric. HITL lifecycle (admin
    accept/reject for AI suggestions). Partial unique on (workspace, name)
    WHERE not archived — archiving frees the name.
  * ``join_hint`` — workspace-scoped join hint between two tables.
    Cascades when either side table is removed.
  * ``description_version`` — append-only versioning per (scope, parent_id);
    captures DDL + samples + stats used at AI generation time for eval replay.

Enum types created:

  * ``da_source_type``        (postgres, snowflake, bigquery, mysql, oracle)
  * ``da_connection_status``  (pending_auth, active, degraded, error, disabled)
  * ``da_table_type``         (table, view, materialized_view)
  * ``da_metric_source``      (admin_authored, ai_suggested, ai_accepted_by_admin)
  * ``da_join_hint_source``   (admin_authored, inferred_from_fk, ai_suggested, ai_accepted_by_admin)
  * ``da_join_type``          (inner, left, right, full)
  * ``da_description_scope``  (table, column, metric, join_hint)
  * ``da_description_source`` (native_comment, ai_generated, ai_suggested, admin_edited)

PII tags applied at create time per ``our-engineering-standards.md`` §13:

  * ``da_connection.credentials``                  pii:credentials
  * ``workspace_metadata_column.sample_values``    pii:freetext
  * ``description_version.inputs_snapshot``        pii:freetext

The C6 anonymization runner reads ``pg_description`` to discover these
columns; untagged PII would be a hidden compliance gap.

Revision ID: v9w0x1y2z3a4
Revises: u8v9w0x1y2z3
Create Date: 2026-05-11 18:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "v9w0x1y2z3a4"
down_revision: Union[str, Sequence[str], None] = "u8v9w0x1y2z3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ---------------------------------------------------------------------------
# Enum types — created once, referenced from multiple tables via
# postgresql.ENUM(name=..., create_type=False).
# ---------------------------------------------------------------------------

_SOURCE_TYPE_VALUES = ("postgres", "snowflake", "bigquery", "mysql", "oracle")
_CONNECTION_STATUS_VALUES = (
    "pending_auth", "active", "degraded", "error", "disabled",
)
_TABLE_TYPE_VALUES = ("table", "view", "materialized_view")
_METRIC_SOURCE_VALUES = (
    "admin_authored", "ai_suggested", "ai_accepted_by_admin",
)
_JOIN_HINT_SOURCE_VALUES = (
    "admin_authored", "inferred_from_fk", "ai_suggested", "ai_accepted_by_admin",
)
_JOIN_TYPE_VALUES = ("inner", "left", "right", "full")
_DESCRIPTION_SCOPE_VALUES = ("table", "column", "metric", "join_hint")
_DESCRIPTION_SOURCE_VALUES = (
    "native_comment", "ai_generated", "ai_suggested", "admin_edited",
)


def upgrade() -> None:
    bind = op.get_bind()

    # Create all enum types first so subsequent table references can use
    # create_type=False.
    postgresql.ENUM(*_SOURCE_TYPE_VALUES, name="da_source_type").create(bind, checkfirst=True)
    postgresql.ENUM(*_CONNECTION_STATUS_VALUES, name="da_connection_status").create(bind, checkfirst=True)
    postgresql.ENUM(*_TABLE_TYPE_VALUES, name="da_table_type").create(bind, checkfirst=True)
    postgresql.ENUM(*_METRIC_SOURCE_VALUES, name="da_metric_source").create(bind, checkfirst=True)
    postgresql.ENUM(*_JOIN_HINT_SOURCE_VALUES, name="da_join_hint_source").create(bind, checkfirst=True)
    postgresql.ENUM(*_JOIN_TYPE_VALUES, name="da_join_type").create(bind, checkfirst=True)
    postgresql.ENUM(*_DESCRIPTION_SCOPE_VALUES, name="da_description_scope").create(bind, checkfirst=True)
    postgresql.ENUM(*_DESCRIPTION_SOURCE_VALUES, name="da_description_source").create(bind, checkfirst=True)

    # -------- da_connection (tenant-level) --------
    op.create_table(
        "da_connection",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("tenant.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "source_type",
            postgresql.ENUM(name="da_source_type", create_type=False),
            nullable=False,
        ),
        sa.Column("connection_name", sa.String(length=255), nullable=False),
        sa.Column(
            "credentials",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            comment="pii:credentials",
        ),
        sa.Column(
            "status",
            postgresql.ENUM(name="da_connection_status", create_type=False),
            nullable=False,
            server_default=sa.text("'pending_auth'"),
        ),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
        ),
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
        "ux_da_connection_tenant_source_name",
        "da_connection",
        ["tenant_id", "source_type", "connection_name"],
        unique=True,
    )
    op.create_index(
        "ix_da_connection_tenant",
        "da_connection",
        ["tenant_id"],
    )

    # -------- workspace_metadata_connection --------
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

    # -------- workspace_metadata_table --------
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
            sa.ForeignKey("workspace_metadata_connection.id", ondelete="CASCADE"),
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

    # -------- workspace_metadata_column --------
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
            sa.ForeignKey("workspace_metadata_table.id", ondelete="CASCADE"),
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
        sa.Column("foreign_key_to", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
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
        sa.Column("statistical_profile", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("synonyms", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("unit", sa.String(length=64), nullable=True),
        sa.Column("format_hint", sa.String(length=64), nullable=True),
        sa.Column("valid_aggregations", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
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

    # -------- metric --------
    op.create_table(
        "metric",
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
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("sql_expression", sa.Text(), nullable=False),
        sa.Column("filters", sa.Text(), nullable=True),
        sa.Column(
            "applicable_tables",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("valid_dimensions", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "source",
            postgresql.ENUM(name="da_metric_source", create_type=False),
            nullable=False,
            server_default=sa.text("'admin_authored'"),
        ),
        sa.Column(
            "accepted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "updated_by",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("last_used_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "is_archived",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
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
        "ux_metric_workspace_name_active",
        "metric",
        ["workspace_id", "name"],
        unique=True,
        postgresql_where=sa.text("is_archived = false"),
    )
    op.create_index(
        "ix_metric_workspace",
        "metric",
        ["workspace_id"],
    )

    # -------- join_hint --------
    op.create_table(
        "join_hint",
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
            "left_table_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("workspace_metadata_table.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("left_columns", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "right_table_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("workspace_metadata_table.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("right_columns", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "join_type",
            postgresql.ENUM(name="da_join_type", create_type=False),
            nullable=False,
            server_default=sa.text("'inner'"),
        ),
        sa.Column("semantic_description", sa.Text(), nullable=True),
        sa.Column(
            "source",
            postgresql.ENUM(name="da_join_hint_source", create_type=False),
            nullable=False,
            server_default=sa.text("'admin_authored'"),
        ),
        sa.Column(
            "accepted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "is_archived",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_join_hint_workspace", "join_hint", ["workspace_id"])
    op.create_index("ix_join_hint_left_table", "join_hint", ["left_table_id"])
    op.create_index("ix_join_hint_right_table", "join_hint", ["right_table_id"])

    # -------- description_version --------
    op.create_table(
        "description_version",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "scope",
            postgresql.ENUM(name="da_description_scope", create_type=False),
            nullable=False,
        ),
        # Soft FK — references one of four parent tables depending on `scope`.
        sa.Column("parent_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column(
            "source",
            postgresql.ENUM(name="da_description_source", create_type=False),
            nullable=False,
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "generated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "generated_by",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "inputs_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="pii:freetext",
        ),
    )
    op.create_index(
        "ux_description_version_parent_version",
        "description_version",
        ["scope", "parent_id", "version_number"],
        unique=True,
    )
    op.create_index(
        "ix_description_version_parent_latest",
        "description_version",
        ["scope", "parent_id", sa.text("version_number DESC")],
    )


def downgrade() -> None:
    # Indexes drop with the table; explicit drop_table calls in reverse FK
    # order (description_version + join_hint + metric reference
    # workspace_metadata_table; workspace_metadata_column references
    # workspace_metadata_table; workspace_metadata_table references
    # workspace_metadata_connection; workspace_metadata_connection
    # references da_connection).
    op.drop_table("description_version")
    op.drop_table("join_hint")
    op.drop_table("metric")
    op.drop_table("workspace_metadata_column")
    op.drop_table("workspace_metadata_table")
    op.drop_table("workspace_metadata_connection")
    op.drop_table("da_connection")

    bind = op.get_bind()
    postgresql.ENUM(name="da_description_source").drop(bind, checkfirst=True)
    postgresql.ENUM(name="da_description_scope").drop(bind, checkfirst=True)
    postgresql.ENUM(name="da_join_type").drop(bind, checkfirst=True)
    postgresql.ENUM(name="da_join_hint_source").drop(bind, checkfirst=True)
    postgresql.ENUM(name="da_metric_source").drop(bind, checkfirst=True)
    postgresql.ENUM(name="da_table_type").drop(bind, checkfirst=True)
    postgresql.ENUM(name="da_connection_status").drop(bind, checkfirst=True)
    postgresql.ENUM(name="da_source_type").drop(bind, checkfirst=True)
