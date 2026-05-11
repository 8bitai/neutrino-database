"""
Schema tests for the Data Analytics metadata layer (NEU-1811 DA-P0).

Seven tables encode the DA pillar's per-warehouse curated state. Six are
workspace-scoped — the canonical metadata layer described in
``product-feature-roadmap/data-analytics/data-flow.md`` §4.8. One
(``da_connection``) is tenant-scoped — the trust relationship + warehouse
credentials described in §Step 1 of the same doc.

Service ownership (locked as F4 in ``data-analytics/feature.md``):

  * ``connector-service`` owns lifecycle CRUD on ``da_connection`` (creating
    / updating / deleting tenant-level connections, holding adapter
    abstractions, executing SQL).
  * ``agent-platform`` owns every write to the six workspace-scoped tables —
    ``workspace_metadata_connection``, ``workspace_metadata_table``,
    ``workspace_metadata_column``, ``metric``, ``join_hint``,
    ``description_version`` — plus all LLM calls (description generation,
    T2S, semantic-layer work).

This file pins the canonical schema shape:

  * presence of each table
  * column names + types + nullability
  * FK wiring with cascade / SET NULL behaviour
  * PII tags on credentials, samples, and replay inputs
  * uniqueness invariants per spec
  * append-only invariant on ``description_version`` (no ``updated_at``)

The test is schema-shape only — round-trip ORM behaviour (inserting rows
and reading them back) lands once the ORM wrappers are in place.

Design source: ``product-feature-roadmap/data-analytics/data-flow.md`` §4.8.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _table_exists(test_engine, table_name: str) -> bool:
    async with test_engine.connect() as conn:
        return await conn.run_sync(
            lambda sync_conn: sa.inspect(sync_conn).has_table(table_name)
        )


async def _columns(test_engine, table_name: str) -> dict:
    async with test_engine.connect() as conn:
        return await conn.run_sync(
            lambda sync_conn: {
                c["name"]: c
                for c in sa.inspect(sync_conn).get_columns(table_name)
            }
        )


async def _foreign_keys(test_engine, table_name: str) -> list[dict]:
    async with test_engine.connect() as conn:
        return await conn.run_sync(
            lambda sync_conn: sa.inspect(sync_conn).get_foreign_keys(table_name)
        )


async def _indexes(test_engine, table_name: str) -> list[dict]:
    async with test_engine.connect() as conn:
        return await conn.run_sync(
            lambda sync_conn: sa.inspect(sync_conn).get_indexes(table_name)
        )


def _ondelete(fk: dict) -> str | None:
    return (fk.get("options") or {}).get("ondelete")


# ---------------------------------------------------------------------------
# Table 1 — da_connection (tenant-level Connection per data-flow.md Step 1)
# ---------------------------------------------------------------------------


class TestDAConnectionTable:
    @pytest.mark.asyncio
    async def test_table_exists(self, test_engine):
        assert await _table_exists(test_engine, "da_connection"), (
            "da_connection is the tenant-level DA Connection table per "
            "data-flow.md Step 1 — one row per tenant warehouse credential."
        )

    @pytest.mark.asyncio
    async def test_required_columns(self, test_engine):
        cols = await _columns(test_engine, "da_connection")
        expected = {
            "id",
            "tenant_id",
            "source_type",
            "connection_name",
            "credentials",
            "status",
            "allowed_schemas",
            "created_by",
            "created_at",
            "updated_at",
        }
        missing = expected - cols.keys()
        assert not missing, f"da_connection missing required columns: {missing}"

    @pytest.mark.asyncio
    async def test_allowed_schemas_is_nullable_jsonb(self, test_engine):
        """``allowed_schemas`` restricts which warehouse schemas Neutrino
        is allowed to access for this connection. NULL means
        unrestricted (Tenant Admin opted to allow everything); a list
        of names is the whitelist (Tenant Admin restricted it).

        Must be JSONB (storing a list[str]) and nullable so existing
        connections backfill cleanly with NULL = unrestricted.
        """
        cols = await _columns(test_engine, "da_connection")
        assert "allowed_schemas" in cols, (
            "da_connection.allowed_schemas required for tenant-level "
            "schema allowlist (NEU-1811 DA-P1f)."
        )
        col = cols["allowed_schemas"]
        assert col["nullable"] is True, (
            "allowed_schemas must be nullable — NULL is the unrestricted "
            "state; existing connections backfill cleanly."
        )
        # SQLAlchemy reports JSONB as `JSONB` instance.
        type_str = str(col["type"]).upper()
        assert "JSONB" in type_str, (
            f"allowed_schemas must be JSONB (list[str]); got type={type_str!r}"
        )

    @pytest.mark.asyncio
    async def test_credentials_is_pii_tagged(self, test_engine):
        """``credentials`` holds warehouse passwords / OAuth tokens. PII-tag
        at create time per our-engineering-standards.md §13 so the C6
        anonymization runner can find it later.
        """
        cols = await _columns(test_engine, "da_connection")
        comment = cols["credentials"].get("comment") or ""
        assert "pii:credentials" in comment, (
            "da_connection.credentials must be tagged 'pii:credentials' "
            "(warehouse secrets); got comment={comment!r}".format(comment=comment)
        )

    @pytest.mark.asyncio
    async def test_tenant_fk_cascade(self, test_engine):
        fks = await _foreign_keys(test_engine, "da_connection")
        matching = [fk for fk in fks if "tenant_id" in fk["constrained_columns"]]
        assert len(matching) == 1, (
            f"da_connection.tenant_id should have exactly one FK to tenant(id); "
            f"got {matching!r}"
        )
        assert matching[0]["referred_table"] == "tenant"
        assert matching[0]["referred_columns"] == ["id"]
        assert _ondelete(matching[0]) == "CASCADE", (
            "Deleting the tenant must cascade-delete its DA connections."
        )

    @pytest.mark.asyncio
    async def test_created_by_fk_set_null(self, test_engine):
        """``created_by`` FK to ``user(id)`` ON DELETE SET NULL — anonymization
        (GDPR Art. 17) must not destroy the connection itself.
        """
        fks = await _foreign_keys(test_engine, "da_connection")
        cb_fk = [fk for fk in fks if "created_by" in fk["constrained_columns"]]
        assert cb_fk, "da_connection.created_by should FK to user(id)"
        assert cb_fk[0]["referred_table"] == "user"
        assert _ondelete(cb_fk[0]) == "SET NULL", (
            "da_connection.created_by must be ON DELETE SET NULL (GDPR-safe "
            "anonymization without destroying the connection)."
        )

    @pytest.mark.asyncio
    async def test_unique_per_tenant_source_name(self, test_engine):
        """Per data-flow.md §1: connection name unique per
        (tenant_id, source_type). Two Snowflake connections in one tenant
        can't both be named "Prod"; one Snowflake + one Postgres both
        named "Prod" is fine.
        """
        indexes = await _indexes(test_engine, "da_connection")
        unique = [
            idx
            for idx in indexes
            if idx.get("unique")
            and set(idx.get("column_names") or [])
            == {"tenant_id", "source_type", "connection_name"}
        ]
        assert unique, (
            "Expected unique index over (tenant_id, source_type, connection_name) "
            f"per data-flow.md §1; got indexes={indexes!r}"
        )


# ---------------------------------------------------------------------------
# Table 2 — workspace_metadata_connection (Entity 2 in §4.8)
# ---------------------------------------------------------------------------


class TestWorkspaceMetadataConnectionTable:
    @pytest.mark.asyncio
    async def test_table_exists(self, test_engine):
        assert await _table_exists(test_engine, "workspace_metadata_connection")

    @pytest.mark.asyncio
    async def test_required_columns(self, test_engine):
        cols = await _columns(test_engine, "workspace_metadata_connection")
        expected = {
            "id",
            "workspace_id",
            "connection_id",
            "source_type",
            "connection_name",
            "database_name",
            "schema_name",
            "schema_description",
            "last_synced_at",
            "created_at",
            "updated_at",
        }
        missing = expected - cols.keys()
        assert not missing, (
            f"workspace_metadata_connection missing required columns: {missing}"
        )

    @pytest.mark.asyncio
    async def test_workspace_fk_cascade(self, test_engine):
        fks = await _foreign_keys(test_engine, "workspace_metadata_connection")
        ws_fk = [fk for fk in fks if "workspace_id" in fk["constrained_columns"]]
        assert ws_fk and ws_fk[0]["referred_table"] == "workspace"
        assert _ondelete(ws_fk[0]) == "CASCADE", (
            "Deleting a workspace must remove its curated DA metadata."
        )

    @pytest.mark.asyncio
    async def test_connection_fk_cascade(self, test_engine):
        fks = await _foreign_keys(test_engine, "workspace_metadata_connection")
        conn_fk = [fk for fk in fks if "connection_id" in fk["constrained_columns"]]
        assert conn_fk and conn_fk[0]["referred_table"] == "da_connection"
        assert _ondelete(conn_fk[0]) == "CASCADE", (
            "Removing a tenant connection must remove the workspace curation "
            "rows that pointed at it."
        )

    @pytest.mark.asyncio
    async def test_uniqueness_per_workspace_conn_db_schema(self, test_engine):
        """§4.8 Entity 2: 'One row per
        (workspace_id, connection_id, database_name, schema_name).'
        """
        indexes = await _indexes(test_engine, "workspace_metadata_connection")
        unique = [
            idx
            for idx in indexes
            if idx.get("unique")
            and set(idx.get("column_names") or [])
            == {"workspace_id", "connection_id", "database_name", "schema_name"}
        ]
        assert unique, (
            "Expected unique index over "
            "(workspace_id, connection_id, database_name, schema_name) per §4.8 Entity 2; "
            f"got {indexes!r}"
        )


# ---------------------------------------------------------------------------
# Table 3 — workspace_metadata_table (Entity 3 in §4.8)
# ---------------------------------------------------------------------------


class TestWorkspaceMetadataTableTable:
    @pytest.mark.asyncio
    async def test_table_exists(self, test_engine):
        assert await _table_exists(test_engine, "workspace_metadata_table")

    @pytest.mark.asyncio
    async def test_required_columns(self, test_engine):
        cols = await _columns(test_engine, "workspace_metadata_table")
        expected = {
            "id",
            "workspace_metadata_connection_id",
            # DDL-derived
            "table_name",
            "table_type",
            "native_comment",
            "row_count",
            # Logical / display
            "table_logical_name",
            # Descriptions (precedence: admin_seed > ai_generated > native_comment)
            "admin_seed_description",
            "ai_generated_description",
            # Curation + tracking
            "is_included",
            "is_archived",
            "last_enriched_at",
            "created_at",
            "updated_at",
        }
        missing = expected - cols.keys()
        assert not missing, (
            f"workspace_metadata_table missing required columns: {missing}"
        )

    @pytest.mark.asyncio
    async def test_connection_fk_cascade(self, test_engine):
        fks = await _foreign_keys(test_engine, "workspace_metadata_table")
        c_fk = [
            fk for fk in fks
            if "workspace_metadata_connection_id" in fk["constrained_columns"]
        ]
        assert c_fk and c_fk[0]["referred_table"] == "workspace_metadata_connection"
        assert _ondelete(c_fk[0]) == "CASCADE"

    @pytest.mark.asyncio
    async def test_uniqueness_per_connection_table_name(self, test_engine):
        indexes = await _indexes(test_engine, "workspace_metadata_table")
        unique = [
            idx
            for idx in indexes
            if idx.get("unique")
            and set(idx.get("column_names") or [])
            == {"workspace_metadata_connection_id", "table_name"}
        ]
        assert unique, (
            "Expected unique (workspace_metadata_connection_id, table_name); "
            f"got {indexes!r}"
        )


# ---------------------------------------------------------------------------
# Table 4 — workspace_metadata_column (Entity 4 in §4.8)
# ---------------------------------------------------------------------------


class TestWorkspaceMetadataColumnTable:
    @pytest.mark.asyncio
    async def test_table_exists(self, test_engine):
        assert await _table_exists(test_engine, "workspace_metadata_column")

    @pytest.mark.asyncio
    async def test_required_columns(self, test_engine):
        cols = await _columns(test_engine, "workspace_metadata_column")
        expected = {
            "id",
            "workspace_metadata_table_id",
            # DDL-derived
            "column_name",
            "data_type",
            "nullable",
            "is_primary_key",
            "is_foreign_key",
            "foreign_key_to",
            "native_comment",
            "ordinal_position",
            # Logical / display
            "column_logical_name",
            # Descriptions
            "admin_seed_description",
            "ai_generated_description",
            # Privacy / access
            "is_pii",
            "is_restricted",
            "allow_sample_values",
            # Phase-2 enrichment (admin opt-in)
            "sample_values",
            "cardinality_score",
            "statistical_profile",
            # Semantic enrichment
            "synonyms",
            "unit",
            "format_hint",
            "valid_aggregations",
            # Curation + tracking
            "is_included",
            "is_archived",
            "last_enriched_at",
            "created_at",
            "updated_at",
        }
        missing = expected - cols.keys()
        assert not missing, (
            f"workspace_metadata_column missing required columns: {missing}"
        )

    @pytest.mark.asyncio
    async def test_table_fk_cascade(self, test_engine):
        fks = await _foreign_keys(test_engine, "workspace_metadata_column")
        t_fk = [
            fk for fk in fks
            if "workspace_metadata_table_id" in fk["constrained_columns"]
        ]
        assert t_fk and t_fk[0]["referred_table"] == "workspace_metadata_table"
        assert _ondelete(t_fk[0]) == "CASCADE"

    @pytest.mark.asyncio
    async def test_sample_values_is_pii_tagged(self, test_engine):
        """``sample_values`` holds admin-pulled real values from the source
        warehouse — can contain customer PII (emails, addresses). Tag for
        the GDPR anonymization runner so it can null these out on erasure.
        """
        cols = await _columns(test_engine, "workspace_metadata_column")
        comment = cols["sample_values"].get("comment") or ""
        assert "pii:freetext" in comment, (
            "workspace_metadata_column.sample_values must be tagged "
            "'pii:freetext' (real values may contain customer PII)."
        )

    @pytest.mark.asyncio
    async def test_uniqueness_per_table_column_name(self, test_engine):
        indexes = await _indexes(test_engine, "workspace_metadata_column")
        unique = [
            idx
            for idx in indexes
            if idx.get("unique")
            and set(idx.get("column_names") or [])
            == {"workspace_metadata_table_id", "column_name"}
        ]
        assert unique, (
            "Expected unique (workspace_metadata_table_id, column_name); "
            f"got {indexes!r}"
        )


# ---------------------------------------------------------------------------
# Table 5 — metric (Entity 5 in §4.8)
# ---------------------------------------------------------------------------


class TestMetricTable:
    @pytest.mark.asyncio
    async def test_table_exists(self, test_engine):
        assert await _table_exists(test_engine, "metric")

    @pytest.mark.asyncio
    async def test_required_columns(self, test_engine):
        cols = await _columns(test_engine, "metric")
        expected = {
            "id",
            "workspace_id",
            "name",
            "description",
            "sql_expression",
            "filters",
            "applicable_tables",
            "valid_dimensions",
            "source",
            "accepted",
            "created_by",
            "updated_by",
            "last_used_at",
            "is_archived",
            "created_at",
            "updated_at",
        }
        missing = expected - cols.keys()
        assert not missing, f"metric missing required columns: {missing}"

    @pytest.mark.asyncio
    async def test_workspace_fk_cascade(self, test_engine):
        fks = await _foreign_keys(test_engine, "metric")
        ws_fk = [fk for fk in fks if "workspace_id" in fk["constrained_columns"]]
        assert ws_fk and ws_fk[0]["referred_table"] == "workspace"
        assert _ondelete(ws_fk[0]) == "CASCADE"

    @pytest.mark.asyncio
    async def test_actor_fks_set_null(self, test_engine):
        """``created_by`` and ``updated_by`` FK to ``user(id)`` ON DELETE
        SET NULL — anonymization must not erase metric audit history.
        """
        fks = await _foreign_keys(test_engine, "metric")
        for col in ("created_by", "updated_by"):
            actor_fk = [fk for fk in fks if col in fk["constrained_columns"]]
            assert actor_fk, f"metric.{col} should FK to user(id)"
            assert actor_fk[0]["referred_table"] == "user"
            assert _ondelete(actor_fk[0]) == "SET NULL", (
                f"metric.{col} must be ON DELETE SET NULL for GDPR-safe anonymization."
            )

    @pytest.mark.asyncio
    async def test_active_name_unique_per_workspace(self, test_engine):
        """Only one ACTIVE metric per (workspace_id, name). Archived rows
        don't block re-creating the name — partial unique index where
        is_archived = false.
        """
        indexes = await _indexes(test_engine, "metric")
        unique = [
            idx
            for idx in indexes
            if idx.get("unique")
            and set(idx.get("column_names") or []) == {"workspace_id", "name"}
        ]
        assert unique, (
            "Expected unique index over (workspace_id, name) on metric; "
            f"got {indexes!r}"
        )
        partial = [
            idx
            for idx in unique
            if (idx.get("dialect_options") or {}).get("postgresql_where") is not None
            or "is_archived" in str(idx)
        ]
        assert partial, (
            "metric (workspace_id, name) unique index must be partial "
            "(WHERE is_archived = false) so archived metrics don't block "
            f"reuse of their name. Got {unique!r}"
        )


# ---------------------------------------------------------------------------
# Table 6 — join_hint (Entity 6 in §4.8)
# ---------------------------------------------------------------------------


class TestJoinHintTable:
    @pytest.mark.asyncio
    async def test_table_exists(self, test_engine):
        assert await _table_exists(test_engine, "join_hint")

    @pytest.mark.asyncio
    async def test_required_columns(self, test_engine):
        cols = await _columns(test_engine, "join_hint")
        expected = {
            "id",
            "workspace_id",
            "left_table_id",
            "left_columns",
            "right_table_id",
            "right_columns",
            "join_type",
            "semantic_description",
            "source",
            "accepted",
            "created_by",
            "is_archived",
            "created_at",
        }
        missing = expected - cols.keys()
        assert not missing, f"join_hint missing required columns: {missing}"

    @pytest.mark.asyncio
    async def test_workspace_fk_cascade(self, test_engine):
        fks = await _foreign_keys(test_engine, "join_hint")
        ws_fk = [fk for fk in fks if "workspace_id" in fk["constrained_columns"]]
        assert ws_fk and ws_fk[0]["referred_table"] == "workspace"
        assert _ondelete(ws_fk[0]) == "CASCADE"

    @pytest.mark.asyncio
    async def test_left_right_table_fks_cascade(self, test_engine):
        """Both side tables of the join must cascade-delete the hint — a
        deleted table invalidates the join.
        """
        fks = await _foreign_keys(test_engine, "join_hint")
        for col in ("left_table_id", "right_table_id"):
            t_fk = [fk for fk in fks if col in fk["constrained_columns"]]
            assert t_fk, f"join_hint.{col} should FK to workspace_metadata_table(id)"
            assert t_fk[0]["referred_table"] == "workspace_metadata_table"
            assert _ondelete(t_fk[0]) == "CASCADE", (
                f"join_hint.{col} must cascade — deleted table invalidates the join."
            )

    @pytest.mark.asyncio
    async def test_created_by_fk_set_null(self, test_engine):
        fks = await _foreign_keys(test_engine, "join_hint")
        cb_fk = [fk for fk in fks if "created_by" in fk["constrained_columns"]]
        assert cb_fk and cb_fk[0]["referred_table"] == "user"
        assert _ondelete(cb_fk[0]) == "SET NULL"


# ---------------------------------------------------------------------------
# Table 7 — description_version (Entity 8 in §4.8) — append-only history
# ---------------------------------------------------------------------------


class TestDescriptionVersionTable:
    @pytest.mark.asyncio
    async def test_table_exists(self, test_engine):
        assert await _table_exists(test_engine, "description_version")

    @pytest.mark.asyncio
    async def test_required_columns(self, test_engine):
        cols = await _columns(test_engine, "description_version")
        expected = {
            "id",
            "scope",
            "parent_id",
            "version_number",
            "source",
            "content",
            "generated_at",
            "generated_by",
            "inputs_snapshot",
        }
        missing = expected - cols.keys()
        assert not missing, (
            f"description_version missing required columns: {missing}"
        )

    @pytest.mark.asyncio
    async def test_no_updated_at_column(self, test_engine):
        """description_version is append-only per §4.5: each correction is
        a new version, not an in-place edit. An ``updated_at`` column
        would signal mutability and violate the design contract.
        """
        cols = await _columns(test_engine, "description_version")
        assert "updated_at" not in cols, (
            "description_version is append-only (§4.5); no updated_at column."
        )

    @pytest.mark.asyncio
    async def test_inputs_snapshot_is_pii_tagged(self, test_engine):
        """``inputs_snapshot`` captures sample_values used to generate the
        AI description (for eval replay). Sample values can contain PII;
        tag accordingly so anonymization sweeps it.
        """
        cols = await _columns(test_engine, "description_version")
        comment = cols["inputs_snapshot"].get("comment") or ""
        assert "pii:freetext" in comment, (
            "description_version.inputs_snapshot must be tagged 'pii:freetext' "
            "(snapshot may contain sample_values with customer PII)."
        )

    @pytest.mark.asyncio
    async def test_generated_by_fk_set_null(self, test_engine):
        """``generated_by`` FK to ``user(id)`` ON DELETE SET NULL —
        anonymization must not destroy the version history itself.
        """
        fks = await _foreign_keys(test_engine, "description_version")
        gb_fk = [fk for fk in fks if "generated_by" in fk["constrained_columns"]]
        assert gb_fk, "description_version.generated_by should FK to user(id)"
        assert gb_fk[0]["referred_table"] == "user"
        assert _ondelete(gb_fk[0]) == "SET NULL"

    @pytest.mark.asyncio
    async def test_version_number_uniqueness(self, test_engine):
        """A description can only have one row per version number — versions
        are auto-incremented per (scope, parent_id).
        """
        indexes = await _indexes(test_engine, "description_version")
        unique = [
            idx
            for idx in indexes
            if idx.get("unique")
            and set(idx.get("column_names") or [])
            == {"scope", "parent_id", "version_number"}
        ]
        assert unique, (
            "Expected unique (scope, parent_id, version_number) on "
            f"description_version; got {indexes!r}"
        )
