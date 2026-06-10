"""WF-CF-1b.1 — workspace_integration_settings schema.

Per-workspace connector governance policy. Pure metadata + ORM shape checks
(no DB) — the migration↔metadata parity is exercised by the suite's apply.
"""

from __future__ import annotations

from neutrino_database.models import tables


def test_table_registered():
    assert "workspace_integration_settings" in tables.metadata.tables


def test_columns_and_primary_key():
    t = tables.workspace_integration_settings
    assert {c.name for c in t.columns} == {
        "workspace_id",
        "allow_personal_integrations",
        "allow_personal_scoped_workflows",
        "created_at",
        "updated_at",
    }
    assert t.c.workspace_id.primary_key


def test_policy_defaults_are_permissive_and_not_null():
    t = tables.workspace_integration_settings
    for col in ("allow_personal_integrations", "allow_personal_scoped_workflows"):
        assert t.c[col].nullable is False
        assert t.c[col].server_default is not None  # fail-safe = true


def test_orm_maps_to_table():
    from neutrino_database.models.orm import WorkspaceIntegrationSettings

    assert (
        WorkspaceIntegrationSettings.__table__
        is tables.workspace_integration_settings
    )
