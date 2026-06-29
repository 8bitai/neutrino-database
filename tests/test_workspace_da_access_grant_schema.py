"""
X-DA-ACL-1 — Per-member column-level access control for Data Analytics.

Schema-shape tests for the ``workspace_da_access_grant`` table.

The table is the projection of per-member ACL decisions on DA catalog
resources (schemas / tables / columns) within a workspace. Mature
systems (Notion page-share, Drive folder ACL) all converge on the
same shape: nested resource types with inherited relations + an
explicit-deny override (OpenFGA's ``but not`` pattern). We store the
grants in Postgres as the source of truth for the UI matrix +
agent-platform's local enforcement; OpenFGA tuples become a
write-through layer when distributed checks land in a follow-up.

Locked semantics:

  * Default: workspace member has access to whatever the workspace
    curated (no row in this table for that member × resource =
    "inherit from parent"). The deepest no-row level falls through
    to workspace membership.
  * ``effect='allow'`` row = explicit grant. Used when admin needs
    to grant access on a child that the parent denies.
  * ``effect='deny'`` row = explicit revoke at this level.
  * Resolution rule (encoded in the service, not the schema):
    closest level wins; deny beats allow at the same level. Tenant
    Owner / Tenant Admin / Workspace Admin bypass unconditionally
    via the JWT projection.
  * M10 catalog flags (PII / Restricted) hard-block above all of
    this, regardless of grants.

This file pins the schema shape. Tests fail before the migration +
``tables.py`` change land; pass after.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa


# ---------------------------------------------------------------------------
# Helpers (parity with test_chat_workspace_scoping_schema.py)
# ---------------------------------------------------------------------------


async def _columns(test_engine, table_name: str) -> dict:
    async with test_engine.connect() as conn:
        return await conn.run_sync(
            lambda sync_conn: {
                c["name"]: c
                for c in sa.inspect(sync_conn).get_columns(table_name)
            }
        )


async def _indexes(test_engine, table_name: str) -> list[dict]:
    async with test_engine.connect() as conn:
        return await conn.run_sync(
            lambda sync_conn: sa.inspect(sync_conn).get_indexes(table_name)
        )


async def _foreign_keys(test_engine, table_name: str) -> list[dict]:
    async with test_engine.connect() as conn:
        return await conn.run_sync(
            lambda sync_conn: sa.inspect(sync_conn).get_foreign_keys(table_name)
        )


async def _unique_constraints(test_engine, table_name: str) -> list[dict]:
    async with test_engine.connect() as conn:
        return await conn.run_sync(
            lambda sync_conn: sa.inspect(sync_conn).get_unique_constraints(
                table_name
            )
        )


async def _enum_values(test_engine, enum_name: str) -> list[str]:
    async with test_engine.connect() as conn:
        result = await conn.execute(
            sa.text(
                """
                SELECT e.enumlabel
                FROM pg_type t
                JOIN pg_enum e ON e.enumtypid = t.oid
                WHERE t.typname = :name
                ORDER BY e.enumsortorder
                """
            ),
            {"name": enum_name},
        )
        return [row[0] for row in result.fetchall()]


def _ondelete(fk: dict) -> str | None:
    return (fk.get("options") or {}).get("ondelete")


# ---------------------------------------------------------------------------
# Column shape
# ---------------------------------------------------------------------------


class TestWorkspaceDAAccessGrantColumns:
    @pytest.mark.asyncio
    async def test_required_columns_present_and_not_null(self, test_engine):
        cols = await _columns(test_engine, "workspace_da_access_grant")
        expected = {
            "id",
            "workspace_id",
            "user_id",
            "resource_type",
            "resource_id",
            "effect",
            "created_at",
            "updated_at",
            "created_by",
        }
        missing = expected - set(cols.keys())
        assert not missing, (
            f"workspace_da_access_grant missing columns: {missing}. "
            f"Got: {sorted(cols.keys())}"
        )
        # All identity + grant columns NOT NULL — a NULL on any of
        # these would make the row ambiguous about what's being
        # granted/denied to whom.
        for non_null in (
            "workspace_id",
            "user_id",
            "resource_type",
            "resource_id",
            "effect",
            "created_by",
        ):
            assert cols[non_null]["nullable"] is False, (
                f"{non_null} must be NOT NULL on workspace_da_access_grant"
            )


# ---------------------------------------------------------------------------
# Enum types — resource_type + access_effect
# ---------------------------------------------------------------------------


class TestWorkspaceDAAccessGrantEnums:
    @pytest.mark.asyncio
    async def test_resource_type_enum_values(self, test_engine):
        values = await _enum_values(test_engine, "da_access_resource_type")
        assert set(values) == {"schema", "table", "column"}, (
            "da_access_resource_type must enumerate schema/table/column "
            f"only; got {values}"
        )

    @pytest.mark.asyncio
    async def test_access_effect_enum_values(self, test_engine):
        values = await _enum_values(test_engine, "da_access_effect")
        assert set(values) == {"allow", "deny"}, (
            "da_access_effect must be allow|deny — no third state in "
            "the DB. 'Inherits parent' is the absence of any row."
        )


# ---------------------------------------------------------------------------
# FK + cascade behaviour
# ---------------------------------------------------------------------------


class TestWorkspaceDAAccessGrantForeignKeys:
    """workspace_id and user_id MUST cascade-delete so leaving a
    workspace or losing a user account properly cleans up their
    grant projection rows. Otherwise we'd carry stale grants for
    deleted principals — a real audit headache."""

    @pytest.mark.asyncio
    async def test_workspace_id_cascade(self, test_engine):
        fks = await _foreign_keys(test_engine, "workspace_da_access_grant")
        ws_fk = next(
            (
                fk
                for fk in fks
                if fk["constrained_columns"] == ["workspace_id"]
            ),
            None,
        )
        assert ws_fk is not None
        assert ws_fk["referred_table"] == "workspace"
        assert _ondelete(ws_fk) == "CASCADE", (
            "workspace_id ondelete must be CASCADE — deleting a "
            "workspace must purge its access grants."
        )

    @pytest.mark.asyncio
    async def test_user_id_cascade(self, test_engine):
        fks = await _foreign_keys(test_engine, "workspace_da_access_grant")
        user_fk = next(
            (fk for fk in fks if fk["constrained_columns"] == ["user_id"]),
            None,
        )
        assert user_fk is not None
        assert user_fk["referred_table"] == "user"
        assert _ondelete(user_fk) == "CASCADE", (
            "user_id ondelete must be CASCADE — deleting a user "
            "purges their grants."
        )


# ---------------------------------------------------------------------------
# Uniqueness + index shape for the UI matrix queries
# ---------------------------------------------------------------------------


class TestWorkspaceDAAccessGrantUniqueness:
    @pytest.mark.asyncio
    async def test_one_row_per_member_per_resource(self, test_engine):
        """At most one effect per (member, resource). Without this
        the UI couldn't decide what the 'current state' is for a
        cell in the matrix; conflicting rows would race."""
        ucs = await _unique_constraints(
            test_engine, "workspace_da_access_grant"
        )
        match = [
            uc
            for uc in ucs
            if set(uc["column_names"])
            == {"workspace_id", "user_id", "resource_type", "resource_id"}
        ]
        assert match, (
            "Expected UNIQUE (workspace_id, user_id, resource_type, "
            "resource_id). One row per member per resource only."
        )


class TestWorkspaceDAAccessGrantIndexes:
    """Two read patterns drive every UI query:

      1. "All grants for member B in workspace W" — populates the
         3-state controls down the catalog tree for the Members
         summary view.
      2. "All grants on resource R in workspace W" — populates the
         Access drawer when an admin clicks the chip on a row.

    Each gets its own composite index so neither path scans the
    whole table.
    """

    @pytest.mark.asyncio
    async def test_member_lookup_index_exists(self, test_engine):
        indexes = await _indexes(test_engine, "workspace_da_access_grant")
        match = next(
            (
                ix
                for ix in indexes
                if ix["column_names"][:2] == ["workspace_id", "user_id"]
            ),
            None,
        )
        assert match is not None, (
            "Expected an index leading on (workspace_id, user_id) "
            "for the 'all grants for this member' lookup. Existing: "
            f"{[ix['name'] for ix in indexes]}"
        )

    @pytest.mark.asyncio
    async def test_resource_lookup_index_exists(self, test_engine):
        indexes = await _indexes(test_engine, "workspace_da_access_grant")
        match = next(
            (
                ix
                for ix in indexes
                if ix["column_names"][:3]
                == ["workspace_id", "resource_type", "resource_id"]
            ),
            None,
        )
        assert match is not None, (
            "Expected an index leading on (workspace_id, resource_type, "
            "resource_id) for the 'all members affected by this "
            "resource' lookup. Existing: "
            f"{[ix['name'] for ix in indexes]}"
        )
