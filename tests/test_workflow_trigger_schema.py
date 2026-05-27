"""WF-M3a.2 — workflow_trigger schema (how a workflow gets fired without a click).

One row per trigger attached to a workflow. A webhook trigger carries a unique
``token`` whose public URL (``POST /triggers/{token}``) starts a run with the
request body as the trigger node's payload; cron/event triggers carry their
config instead. Locked semantics:
  * tenant/workspace/workflow scoped (all NOT NULL, cascade) — a trigger dies
    with its workflow.
  * ``node_id`` binds the trigger to the trigger node in the graph.
  * ``token`` is unique (webhook lookup is O(1)) and nullable (cron/event have
    none); ``config`` (JSONB) holds kind-specific settings.
  * ``workflow_run.trigger_id`` gains its FK here (SET NULL — deleting a trigger
    keeps run history, just unlinks it).

Schema-shape only (create_all-backed): fails before tables.py lands, passes after.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa


async def _columns(test_engine, table: str) -> dict:
    async with test_engine.connect() as conn:
        return await conn.run_sync(
            lambda c: {col["name"]: col for col in sa.inspect(c).get_columns(table)}
        )


async def _indexes(test_engine, table: str) -> list[dict]:
    async with test_engine.connect() as conn:
        return await conn.run_sync(lambda c: sa.inspect(c).get_indexes(table))


async def _foreign_keys(test_engine, table: str) -> list[dict]:
    async with test_engine.connect() as conn:
        return await conn.run_sync(lambda c: sa.inspect(c).get_foreign_keys(table))


async def _enum_values(test_engine, enum_name: str) -> list[str]:
    async with test_engine.connect() as conn:
        result = await conn.execute(
            sa.text(
                """
                SELECT e.enumlabel FROM pg_type t
                JOIN pg_enum e ON e.enumtypid = t.oid
                WHERE t.typname = :name ORDER BY e.enumsortorder
                """
            ),
            {"name": enum_name},
        )
        return [row[0] for row in result.fetchall()]


def _ondelete(fk: dict) -> str | None:
    return (fk.get("options") or {}).get("ondelete")


def _fk_to(fks: list[dict], referred_table: str, column: str) -> dict | None:
    for fk in fks:
        if fk["referred_table"] == referred_table and column in fk["constrained_columns"]:
            return fk
    return None


class TestWorkflowTriggerColumns:
    @pytest.mark.asyncio
    async def test_required_columns_present(self, test_engine):
        cols = await _columns(test_engine, "workflow_trigger")
        expected = {
            "id",
            "tenant_id",
            "workspace_id",
            "workflow_id",
            "node_id",
            "kind",
            "token",
            "config",
            "status",
            "created_by",
            "created_at",
            "updated_at",
        }
        assert expected <= set(cols), f"missing: {expected - set(cols)}"

    @pytest.mark.asyncio
    async def test_scoping_and_binding_not_null(self, test_engine):
        cols = await _columns(test_engine, "workflow_trigger")
        for col in ("tenant_id", "workspace_id", "workflow_id", "node_id", "kind", "status", "created_at"):
            assert cols[col]["nullable"] is False, f"{col} should be NOT NULL"

    @pytest.mark.asyncio
    async def test_token_and_creator_nullable(self, test_engine):
        cols = await _columns(test_engine, "workflow_trigger")
        assert cols["token"]["nullable"] is True  # cron/event have no token
        assert cols["created_by"]["nullable"] is True

    @pytest.mark.asyncio
    async def test_config_is_jsonb(self, test_engine):
        cols = await _columns(test_engine, "workflow_trigger")
        assert "JSON" in cols["config"]["type"].__class__.__name__.upper()


class TestWorkflowTriggerEnums:
    @pytest.mark.asyncio
    async def test_kind_enum_values(self, test_engine):
        assert await _enum_values(test_engine, "workflow_trigger_kind") == [
            "webhook",
            "cron",
            "event",
        ]

    @pytest.mark.asyncio
    async def test_status_enum_values(self, test_engine):
        assert await _enum_values(test_engine, "workflow_trigger_status") == [
            "active",
            "disabled",
        ]


class TestWorkflowTriggerForeignKeys:
    @pytest.mark.asyncio
    async def test_tenant_fk_cascade(self, test_engine):
        fk = _fk_to(await _foreign_keys(test_engine, "workflow_trigger"), "tenant", "tenant_id")
        assert fk is not None and _ondelete(fk) == "CASCADE"

    @pytest.mark.asyncio
    async def test_workspace_fk_cascade(self, test_engine):
        fk = _fk_to(await _foreign_keys(test_engine, "workflow_trigger"), "workspace", "workspace_id")
        assert fk is not None and _ondelete(fk) == "CASCADE"

    @pytest.mark.asyncio
    async def test_workflow_fk_cascade(self, test_engine):
        fk = _fk_to(await _foreign_keys(test_engine, "workflow_trigger"), "workflow", "workflow_id")
        assert fk is not None and _ondelete(fk) == "CASCADE"

    @pytest.mark.asyncio
    async def test_creator_fk_set_null(self, test_engine):
        fk = _fk_to(await _foreign_keys(test_engine, "workflow_trigger"), "user", "created_by")
        assert fk is not None and _ondelete(fk) == "SET NULL"


class TestWorkflowTriggerIndexes:
    @pytest.mark.asyncio
    async def test_workflow_index(self, test_engine):
        cols = [tuple(ix["column_names"]) for ix in await _indexes(test_engine, "workflow_trigger")]
        assert ("workflow_id",) in cols

    @pytest.mark.asyncio
    async def test_token_unique(self, test_engine):
        indexes = await _indexes(test_engine, "workflow_trigger")
        token_idx = [ix for ix in indexes if tuple(ix["column_names"]) == ("token",)]
        assert token_idx and token_idx[0]["unique"] is True


class TestWorkflowRunTriggerFk:
    @pytest.mark.asyncio
    async def test_run_trigger_fk_set_null(self, test_engine):
        # workflow_run.trigger_id gains its FK now that the table exists.
        fk = _fk_to(await _foreign_keys(test_engine, "workflow_run"), "workflow_trigger", "trigger_id")
        assert fk is not None and _ondelete(fk) == "SET NULL"
