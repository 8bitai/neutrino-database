"""NC-103 — da_enrichment_run + da_enrichment_table_item schema.

Durable DA catalog enrichment (Reprofile / Regenerate wired through a
Temporal workflow) needs a DB-backed progress projection the curation page
polls and re-attaches to across refreshes. Two tables:

  * ``da_enrichment_run``        — one row per triggered run (the command +
                                   rollup counters + Temporal handle).
  * ``da_enrichment_table_item`` — per-table, two-stage progress
                                   (``profile_status`` / ``describe_status``)
                                   that drives the live "Profiling…" /
                                   "Generating…" / "Profiled ✓" badges.

Pure metadata + ORM shape checks (no DB); the migration↔metadata parity is
exercised by the suite's apply.
"""

from __future__ import annotations

from neutrino_database.models import tables


# --------------------------------------------------------------------------
# Tables registered on the shared metadata
# --------------------------------------------------------------------------
def test_tables_registered():
    assert "da_enrichment_run" in tables.metadata.tables
    assert "da_enrichment_table_item" in tables.metadata.tables


# --------------------------------------------------------------------------
# da_enrichment_run — the command record + rollup
# --------------------------------------------------------------------------
def test_run_columns_and_primary_key():
    t = tables.da_enrichment_run
    assert {c.name for c in t.columns} == {
        "id",
        "tenant_id",
        "workspace_id",
        "connection_id",
        "scope",
        "operation",
        "schema_id",
        "table_id",
        "status",
        "total_tables",
        "completed_tables",
        "failed_tables",
        "skipped_tables",
        "temporal_workflow_id",
        "temporal_run_id",
        "created_by_user_id",
        "error",
        "created_at",
        "started_at",
        "finished_at",
    }
    assert t.c.id.primary_key


def test_run_scope_and_targets():
    """scope + operation are not-null discriminators; schema_id / table_id are
    nullable targets selected by scope (connection runs carry neither)."""
    t = tables.da_enrichment_run
    assert t.c.scope.nullable is False
    assert t.c.operation.nullable is False
    assert t.c.schema_id.nullable is True
    assert t.c.table_id.nullable is True


def test_run_status_and_counters_default_safely():
    t = tables.da_enrichment_run
    # status starts 'pending' and is never null
    assert t.c.status.nullable is False
    assert t.c.status.server_default is not None
    # rollup counters are not-null and default to 0
    for col in ("total_tables", "completed_tables", "failed_tables", "skipped_tables"):
        assert t.c[col].nullable is False
        assert t.c[col].server_default is not None


def test_run_foreign_keys_cascade():
    t = tables.da_enrichment_run
    fk_targets = {
        next(iter(c.foreign_keys)).column.table.name
        for c in t.columns
        if c.foreign_keys
    }
    # The DA connection is an ``integration`` row (unified integration model).
    assert {"tenant", "workspace", "integration", "da_catalog_schema", "da_catalog_table", "user"} <= fk_targets


# --------------------------------------------------------------------------
# da_enrichment_table_item — per-table two-stage progress
# --------------------------------------------------------------------------
def test_item_columns_and_primary_key():
    t = tables.da_enrichment_table_item
    assert {c.name for c in t.columns} == {
        "id",
        "run_id",
        "da_catalog_table_id",
        "schema_name",
        "table_name",
        "profile_status",
        "describe_status",
        "columns_total",
        "columns_described",
        "error",
        "started_at",
        "finished_at",
        "created_at",
        "updated_at",
    }
    assert t.c.id.primary_key


def test_item_stage_statuses_nullable():
    """A profile-only run leaves describe_status NULL (stage not applicable),
    and vice-versa — so the stage columns must be nullable."""
    t = tables.da_enrichment_table_item
    assert t.c.profile_status.nullable is True
    assert t.c.describe_status.nullable is True


def test_item_unique_table_per_run():
    t = tables.da_enrichment_table_item
    uniques = [
        {c.name for c in con.columns}
        for con in t.constraints
        if con.__class__.__name__ == "UniqueConstraint"
    ]
    assert {"run_id", "da_catalog_table_id"} in uniques


def test_item_run_fk_cascades():
    t = tables.da_enrichment_table_item
    run_fk = next(iter(t.c.run_id.foreign_keys))
    assert run_fk.column.table.name == "da_enrichment_run"
    assert run_fk.ondelete == "CASCADE"


# --------------------------------------------------------------------------
# Enums
# --------------------------------------------------------------------------
def test_enrichment_enums():
    from neutrino_database.models.enums import (
        DAEnrichmentOperationEnum,
        DAEnrichmentRunStatusEnum,
        DAEnrichmentScopeEnum,
        DAEnrichmentStageStatusEnum,
    )

    assert {e.value for e in DAEnrichmentOperationEnum} == {"profile", "describe", "enrich"}
    assert {e.value for e in DAEnrichmentScopeEnum} == {"connection", "schema", "table"}
    assert {e.value for e in DAEnrichmentStageStatusEnum} == {
        "pending",
        "running",
        "done",
        "skipped",
        "failed",
    }
    assert {e.value for e in DAEnrichmentRunStatusEnum} == {
        "pending",
        "running",
        "completed",
        "completed_with_errors",
        "failed",
        "cancelled",
    }


# --------------------------------------------------------------------------
# ORM ↔ Table binding
# --------------------------------------------------------------------------
def test_orm_maps_to_tables():
    from neutrino_database.models.orm import DAEnrichmentRun, DAEnrichmentTableItem

    assert DAEnrichmentRun.__table__ is tables.da_enrichment_run
    assert DAEnrichmentTableItem.__table__ is tables.da_enrichment_table_item
