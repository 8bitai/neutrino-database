"""
X-CHAT-WS-1 — Workspace scoping on the ``chat`` table.

The ``chat`` primitive (used by ES ad-hoc Q&A, DA ad-hoc Q&A, and DA
dashboard-build threads) was originally tenant-scoped:

    chat(tenant_id, created_by, kind, dashboard_id, ...)

That model is wrong for a multi-workspace SaaS — a user who belongs
to two workspaces sees every chat they ever created from any
workspace context. Mature systems (Linear, Notion, Slack channels,
ChatGPT Teams) all scope chat threads to a workspace / channel so
that switching workspaces switches conversation context cleanly.

Beyond UX, this is a SOC2/GDPR data-isolation gap: the gateway list
proxy enforces tenant-membership only (cf. ``send_message`` which
already checks workspace membership at
``neutrino-gateway/app/chats/router.py:125``) — without
``chat.workspace_id`` there is no underlying record on which to
ground per-workspace authorization, so a Tenant Admin sweep that
removes a user from workspace A leaves their old workspace-A
threads visible when they're inside workspace B.

This file pins the corrected schema shape. Tests fail before the
migration + ``tables.py`` change land; pass after.

Locked design points:

  * ``workspace_id`` is NOT NULL. We accept a one-time TRUNCATE of
    ``chat`` + ``message`` in the migration (pre-launch, dev-only
    data) rather than carry a nullable "legacy" column whose query
    paths would have to fork forever. Same call we made for the DA
    catalog refactor (DA-P1g).
  * FK to ``workspace(id)`` with ``ON DELETE CASCADE`` — deleting
    a workspace removes its chats. Matches the dashboards FK shape
    at ``dashboard.workspace_id`` (CASCADE).
  * Partial index ``(workspace_id, created_by, updated_at DESC)
    WHERE deleted_at IS NULL`` — exactly matches the per-user
    per-workspace list query the FE issues. Soft-deleted rows are
    excluded so the index doesn't bloat with compliance-purged
    history.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa


# ---------------------------------------------------------------------------
# Helpers — same shape as test_dashboard_share_links_schema.py
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


async def _partial_index_predicates(
    test_engine, table_name: str
) -> dict[str, str]:
    """Returns {index_name: WHERE clause text} for partial indexes."""
    async with test_engine.connect() as conn:
        result = await conn.execute(
            sa.text(
                """
                SELECT indexname, indexdef
                FROM pg_indexes
                WHERE tablename = :table_name
                """
            ),
            {"table_name": table_name},
        )
        out: dict[str, str] = {}
        for name, indexdef in result.fetchall():
            upper = indexdef.upper()
            where_pos = upper.rfind(" WHERE ")
            if where_pos >= 0:
                out[name] = indexdef[where_pos + len(" WHERE ") :].strip()
        return out


def _ondelete(fk: dict) -> str | None:
    return (fk.get("options") or {}).get("ondelete")


# ---------------------------------------------------------------------------
# workspace_id column shape
# ---------------------------------------------------------------------------


class TestChatWorkspaceIdColumn:
    """Pins that ``chat.workspace_id`` exists, is NOT NULL UUID, and
    is FK to ``workspace.id`` with CASCADE on delete."""

    @pytest.mark.asyncio
    async def test_workspace_id_column_present_and_not_null(self, test_engine):
        cols = await _columns(test_engine, "chat")
        assert "workspace_id" in cols, (
            "chat.workspace_id is the locked authorization-grounding "
            "column for the per-workspace chat list query; without it "
            "tenant-scoped storage cannot enforce workspace isolation. "
            f"Existing columns: {sorted(cols.keys())}"
        )
        col = cols["workspace_id"]
        assert col["nullable"] is False, (
            "chat.workspace_id MUST be NOT NULL — nullable would create "
            "a 'legacy bucket' branch in every query path. Pre-launch "
            "we TRUNCATE existing rows and start clean."
        )

    @pytest.mark.asyncio
    async def test_workspace_id_fk_cascade(self, test_engine):
        fks = await _foreign_keys(test_engine, "chat")
        ws_fk = next(
            (fk for fk in fks if fk["constrained_columns"] == ["workspace_id"]),
            None,
        )
        assert ws_fk is not None, (
            "chat.workspace_id must have a FK to workspace.id; without "
            "it, deleting a workspace orphans its chat rows."
        )
        assert ws_fk["referred_table"] == "workspace"
        assert ws_fk["referred_columns"] == ["id"]
        assert _ondelete(ws_fk) == "CASCADE", (
            "chat.workspace_id FK ondelete must be CASCADE — deleting a "
            "workspace removes its conversational history (same shape "
            "as dashboard.workspace_id, which is also CASCADE)."
        )


# ---------------------------------------------------------------------------
# Partial index for the list query
# ---------------------------------------------------------------------------


class TestChatListIndex:
    """The FE's ``listChats()`` translates to:

        SELECT * FROM chat
        WHERE workspace_id = :ws
          AND created_by   = :user
          AND deleted_at IS NULL
        ORDER BY updated_at DESC

    The partial index keys exactly that predicate. Soft-deleted rows
    are excluded so compliance-purged threads don't bloat the index.
    """

    @pytest.mark.asyncio
    async def test_workspace_user_updated_index_exists(self, test_engine):
        indexes = await _indexes(test_engine, "chat")
        wanted = next(
            (
                ix
                for ix in indexes
                if ix["column_names"][:3]
                == ["workspace_id", "created_by", "updated_at"]
            ),
            None,
        )
        assert wanted is not None, (
            "Expected an index whose leading columns are "
            "(workspace_id, created_by, updated_at) to serve the "
            "per-user per-workspace chat list query. "
            f"Existing indexes: {[ix['name'] for ix in indexes]}"
        )

    @pytest.mark.asyncio
    async def test_list_index_is_partial_on_deleted_at(self, test_engine):
        predicates = await _partial_index_predicates(test_engine, "chat")
        match = [
            (name, pred)
            for name, pred in predicates.items()
            if "workspace" in name.lower() and "deleted_at" in pred.lower()
        ]
        assert match, (
            "The workspace-scoped list index must be partial on "
            "deleted_at IS NULL — without the WHERE clause, the index "
            "bloats with compliance-purged rows that the live list "
            "query never sees. "
            f"Indexes with WHERE: {predicates}"
        )


# ---------------------------------------------------------------------------
# Tenant-scoped indexes — sanity check
# ---------------------------------------------------------------------------


class TestChatLegacyIndexCleanup:
    """The old per-tenant per-user index ``ix_chat_created_by`` (keyed
    ``(tenant_id, created_by)``) was the right shape for tenant-only
    chats. Now that the list query is keyed by ``workspace_id`` the
    old index is redundant — its DELETE removes index-write overhead
    on every chat insert."""

    @pytest.mark.asyncio
    async def test_old_tenant_created_by_index_removed(self, test_engine):
        indexes = await _indexes(test_engine, "chat")
        names = {ix["name"] for ix in indexes}
        assert "ix_chat_created_by" not in names, (
            "ix_chat_created_by (tenant_id, created_by) is superseded "
            "by the workspace-scoped list index; the migration must "
            "drop it. Keeping it adds an unused write cost on every "
            f"chat insert. Existing indexes: {sorted(names)}"
        )
