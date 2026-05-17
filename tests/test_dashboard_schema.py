"""
Schema tests for the Dashboards layer (NEU-1811 DA-P3.1).

Three new tables + one chat extension shipped by the dashboard
authoring epic (D3 / D6 / D7 from
``product-feature-roadmap/data-analytics/data-analytics.md``):

  * ``dashboard`` — the authored surface. One row per saved/published
    dashboard, workspace-scoped, owned by a workspace admin. Visibility
    + status flags drive what shows up in the Library's Drafts vs
    Published sections.
  * ``dashboard_widget`` — the widgets that make up a dashboard. Holds
    layout (x/y/w/h), widget_type, the SQL data binding, the viz spec,
    grounding metadata (which tables / columns drove the answer + who
    curated them — the trust contract carrying through from the chat
    surface), and a back-pointer to the message that proposed it.
  * ``dashboard_link_token`` — shareable URL tokens for external /
    link-only access. Mints anonymous read access to one dashboard;
    expire-able + revocable + audited (accessed_count).
  * ``chat`` table extensions: ``kind`` (``ad_hoc`` | ``dashboard_build``)
    + nullable ``dashboard_id`` FK. Drafts in the Library ARE chat
    threads with ``kind='dashboard_build'``; build conversations and
    ad-hoc Q&A share one chat primitive (D6).

Production-grade pattern (Looker, Sigma, Hex, Mode): dashboards live
in a workspace-scoped library, layered widgets reference data bindings
inline (vs. saved-queries indirection — that's TD-DASH-SAVED-QUERIES-1
for later), share via per-resource link tokens. See DA-P3 design lock
in this session for the four production-grade decisions: 12-col grid
layout, inline SQL data binding, draft/published status, sync agent.

This file pins the canonical schema shape:

  * presence of each new table + chat extensions
  * column names + types + nullability
  * FK wiring (CASCADE from workspace; SET NULL on owner / created_by
    so deleting a user doesn't lose dashboards; CASCADE from dashboard
    to widget + link_token)
  * enum types exist with the expected values
  * uniqueness invariants (dashboard.slug unique within workspace,
    dashboard_link_token.token globally unique)
  * key indexes (workspace_id + status for Library queries; token for
    the public viewer path)

Round-trip ORM tests (inserting + reading rows) land in
``test_dashboard_orm.py`` alongside the ORM wrappers.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa


# ---------------------------------------------------------------------------
# Helpers (mirror test_da_metadata_schema.py)
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


async def _unique_constraints(test_engine, table_name: str) -> list[dict]:
    async with test_engine.connect() as conn:
        return await conn.run_sync(
            lambda sync_conn: sa.inspect(sync_conn).get_unique_constraints(
                table_name
            )
        )


def _ondelete(fk: dict) -> str | None:
    return (fk.get("options") or {}).get("ondelete")


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


# ---------------------------------------------------------------------------
# Enum types
# ---------------------------------------------------------------------------


class TestDashboardEnums:
    @pytest.mark.asyncio
    async def test_dashboard_status_enum(self, test_engine):
        values = await _enum_values(test_engine, "dashboard_status")
        assert set(values) == {"draft", "published"}, (
            "dashboard_status enum must carry draft + published only — the "
            "Library's section split (Drafts | Published) reads off this."
        )

    @pytest.mark.asyncio
    async def test_dashboard_visibility_enum(self, test_engine):
        values = await _enum_values(test_engine, "dashboard_visibility")
        assert set(values) == {
            "workspace_members",
            "restricted",
            "link_only",
        }, (
            "dashboard_visibility enum carries the three v1 share layers. "
            "workspace_members = default for published; restricted = future "
            "(TD-DASH-INTERNAL-SHARE-1); link_only = unlisted, only the "
            "minted link can view (anonymous public)."
        )

    @pytest.mark.asyncio
    async def test_dashboard_widget_type_enum(self, test_engine):
        values = await _enum_values(test_engine, "dashboard_widget_type")
        # v1 widget catalog — matches the chat-demo editor canvas
        # set. Future widget types added via enum extension.
        assert set(values) == {
            "kpi_tile",
            "line_chart",
            "bar_chart",
            "stacked_bar",
            "pie_chart",
            "donut_chart",
            "table",
            "text",
        }, f"dashboard_widget_type enum missing or wrong: got {values}"

    @pytest.mark.asyncio
    async def test_chat_kind_enum(self, test_engine):
        values = await _enum_values(test_engine, "chat_kind")
        assert set(values) == {"ad_hoc", "dashboard_build"}, (
            "chat_kind enum splits ad-hoc Q&A from dashboard build threads "
            "(D6). Drafts in the Library are chat rows with "
            "kind='dashboard_build'."
        )


# ---------------------------------------------------------------------------
# dashboard table
# ---------------------------------------------------------------------------


class TestDashboardTable:
    @pytest.mark.asyncio
    async def test_table_exists(self, test_engine):
        assert await _table_exists(test_engine, "dashboard"), (
            "dashboard table missing — DA-P3.1 migration didn't apply."
        )

    @pytest.mark.asyncio
    async def test_required_columns(self, test_engine):
        cols = await _columns(test_engine, "dashboard")
        expected = {
            "id",
            "tenant_id",
            "workspace_id",
            "slug",
            "name",
            "description",
            "status",
            "visibility",
            "build_chat_id",
            "owner_id",
            "created_by",
            "published_at",
            "created_at",
            "updated_at",
        }
        missing = expected - set(cols)
        assert not missing, f"dashboard columns missing: {missing}"

    @pytest.mark.asyncio
    async def test_status_default_is_draft(self, test_engine):
        cols = await _columns(test_engine, "dashboard")
        status = cols["status"]
        # New dashboards start as drafts. Library renders them in the
        # Drafts section until the owner clicks Publish.
        default = (status.get("default") or "").lower()
        assert "draft" in default, (
            f"dashboard.status must default to 'draft'; got {default!r}"
        )

    @pytest.mark.asyncio
    async def test_visibility_default_is_workspace_members(self, test_engine):
        cols = await _columns(test_engine, "dashboard")
        vis = cols["visibility"]
        default = (vis.get("default") or "").lower()
        assert "workspace_members" in default, (
            f"dashboard.visibility must default to 'workspace_members'; "
            f"got {default!r}"
        )

    @pytest.mark.asyncio
    async def test_workspace_fk_cascades(self, test_engine):
        fks = await _foreign_keys(test_engine, "dashboard")
        ws_fk = next(
            (fk for fk in fks if fk["referred_table"] == "workspace"), None
        )
        assert ws_fk is not None, "dashboard → workspace FK missing"
        assert _ondelete(ws_fk) == "CASCADE", (
            "Deleting a workspace must cascade-delete its dashboards — "
            "we don't keep orphaned dashboards pointing at dead workspaces."
        )

    @pytest.mark.asyncio
    async def test_build_chat_fk_set_null(self, test_engine):
        fks = await _foreign_keys(test_engine, "dashboard")
        chat_fk = next(
            (fk for fk in fks if fk["referred_table"] == "chat"), None
        )
        assert chat_fk is not None, "dashboard → chat FK missing"
        # The build chat can be deleted independently (e.g. compliance
        # purge). Dashboard survives with build_chat_id = NULL — the
        # widgets remain valid; only the build history is gone.
        assert _ondelete(chat_fk) == "SET NULL", (
            f"dashboard.build_chat_id FK ondelete must be SET NULL; "
            f"got {_ondelete(chat_fk)!r}"
        )

    @pytest.mark.asyncio
    async def test_owner_and_created_by_set_null_on_user_delete(
        self, test_engine
    ):
        fks = await _foreign_keys(test_engine, "dashboard")
        user_fks = [fk for fk in fks if fk["referred_table"] == "user"]
        assert len(user_fks) >= 2, (
            "dashboard must FK to user twice (owner_id + created_by); "
            f"got {len(user_fks)}"
        )
        for fk in user_fks:
            assert _ondelete(fk) == "SET NULL", (
                "owner_id / created_by must SET NULL when a user is "
                "deleted; we keep the dashboard but lose attribution."
            )

    @pytest.mark.asyncio
    async def test_slug_unique_within_workspace(self, test_engine):
        # Slug uniqueness is per-workspace (two workspaces can each
        # have a "kpi-board" slug). Library URLs route via slug, so
        # collisions inside a workspace would conflict.
        constraints = await _unique_constraints(test_engine, "dashboard")
        slug_constraint = next(
            (
                c
                for c in constraints
                if set(c["column_names"]) == {"workspace_id", "slug"}
            ),
            None,
        )
        assert slug_constraint is not None, (
            "dashboard needs a UNIQUE (workspace_id, slug) constraint"
        )

    @pytest.mark.asyncio
    async def test_workspace_status_index(self, test_engine):
        # Library query: `WHERE workspace_id = ? AND status = ?` runs
        # on every dashboards page render. Needs a covering index.
        indexes = await _indexes(test_engine, "dashboard")
        assert any(
            set(i["column_names"]) >= {"workspace_id", "status"}
            for i in indexes
        ), (
            "dashboard needs an index covering (workspace_id, status) — "
            "the Library page filters on these every render."
        )


# ---------------------------------------------------------------------------
# dashboard_widget table
# ---------------------------------------------------------------------------


class TestDashboardWidgetTable:
    @pytest.mark.asyncio
    async def test_table_exists(self, test_engine):
        assert await _table_exists(test_engine, "dashboard_widget"), (
            "dashboard_widget table missing — DA-P3.1 migration didn't apply."
        )

    @pytest.mark.asyncio
    async def test_required_columns(self, test_engine):
        cols = await _columns(test_engine, "dashboard_widget")
        expected = {
            "id",
            "dashboard_id",
            "position_x",
            "position_y",
            "position_w",
            "position_h",
            "widget_type",
            "title",
            "description",
            "data_binding",
            "viz_spec",
            "grounding_metadata",
            "created_by_message_id",
            "created_at",
            "updated_at",
        }
        missing = expected - set(cols)
        assert not missing, f"dashboard_widget columns missing: {missing}"

    @pytest.mark.asyncio
    async def test_data_binding_is_jsonb(self, test_engine):
        cols = await _columns(test_engine, "dashboard_widget")
        # data_binding holds { connection_id, schema_name, sql, params? }
        # viz_spec holds { chart_type, x_axis, y_axis, series, format, … }
        # grounding_metadata holds { tables[], columns[], curator }
        # All three are JSONB so we can partial-update specific keys
        # without rewriting the blob.
        for col_name in ("data_binding", "viz_spec", "grounding_metadata"):
            col_type = str(cols[col_name]["type"]).upper()
            assert "JSON" in col_type, (
                f"dashboard_widget.{col_name} must be JSONB; got {col_type}"
            )

    @pytest.mark.asyncio
    async def test_dashboard_fk_cascades(self, test_engine):
        fks = await _foreign_keys(test_engine, "dashboard_widget")
        dash_fk = next(
            (fk for fk in fks if fk["referred_table"] == "dashboard"), None
        )
        assert dash_fk is not None, "dashboard_widget → dashboard FK missing"
        assert _ondelete(dash_fk) == "CASCADE", (
            "Deleting a dashboard must cascade-delete its widgets."
        )

    @pytest.mark.asyncio
    async def test_message_fk_set_null(self, test_engine):
        # The build-chat message that proposed this widget. Used for
        # provenance (`grounded_metadata.created_by`). When messages
        # are purged (compliance), the widget survives with
        # created_by_message_id = NULL — the widget itself is the
        # ground truth, not the chat history.
        fks = await _foreign_keys(test_engine, "dashboard_widget")
        msg_fk = next(
            (fk for fk in fks if fk["referred_table"] == "message"), None
        )
        assert msg_fk is not None, "dashboard_widget → message FK missing"
        assert _ondelete(msg_fk) == "SET NULL"

    @pytest.mark.asyncio
    async def test_dashboard_id_index(self, test_engine):
        # `WHERE dashboard_id = ?` is the canonical render-time query.
        indexes = await _indexes(test_engine, "dashboard_widget")
        assert any(
            i["column_names"] == ["dashboard_id"]
            or (i["column_names"] and i["column_names"][0] == "dashboard_id")
            for i in indexes
        ), "dashboard_widget needs an index on dashboard_id"


# ---------------------------------------------------------------------------
# dashboard_link_token table
# ---------------------------------------------------------------------------


class TestDashboardLinkTokenTable:
    @pytest.mark.asyncio
    async def test_table_exists(self, test_engine):
        assert await _table_exists(test_engine, "dashboard_link_token"), (
            "dashboard_link_token table missing"
        )

    @pytest.mark.asyncio
    async def test_required_columns(self, test_engine):
        cols = await _columns(test_engine, "dashboard_link_token")
        expected = {
            "id",
            "dashboard_id",
            "token",
            "expires_at",
            "revoked_at",
            "created_by",
            "accessed_count",
            "created_at",
        }
        missing = expected - set(cols)
        assert not missing, (
            f"dashboard_link_token columns missing: {missing}"
        )

    @pytest.mark.asyncio
    async def test_token_unique_index(self, test_engine):
        # Token lookup is the hot path on the public /shared/{token}
        # viewer route — unique + indexed is non-negotiable.
        indexes = await _indexes(test_engine, "dashboard_link_token")
        token_idx = next(
            (i for i in indexes if i["column_names"] == ["token"]), None
        )
        assert token_idx is not None, (
            "dashboard_link_token.token needs an index for public viewer "
            "lookup"
        )
        assert token_idx.get("unique") is True, (
            "dashboard_link_token.token must be UNIQUE — collisions break "
            "the anonymous viewer route"
        )

    @pytest.mark.asyncio
    async def test_dashboard_fk_cascades(self, test_engine):
        fks = await _foreign_keys(test_engine, "dashboard_link_token")
        dash_fk = next(
            (fk for fk in fks if fk["referred_table"] == "dashboard"), None
        )
        assert dash_fk is not None
        assert _ondelete(dash_fk) == "CASCADE", (
            "Deleting a dashboard must cascade-delete its share tokens — "
            "otherwise revoked dashboards remain accessible via stale "
            "tokens. Hard cascade is the safe default."
        )

    @pytest.mark.asyncio
    async def test_accessed_count_default_zero(self, test_engine):
        cols = await _columns(test_engine, "dashboard_link_token")
        accessed = cols["accessed_count"]
        default = (accessed.get("default") or "").strip()
        assert "0" in default, (
            f"accessed_count must default to 0; got {default!r}"
        )


# ---------------------------------------------------------------------------
# chat extensions
# ---------------------------------------------------------------------------


class TestChatExtensions:
    @pytest.mark.asyncio
    async def test_chat_has_kind_column(self, test_engine):
        cols = await _columns(test_engine, "chat")
        assert "kind" in cols, (
            "chat.kind column missing — D6 chat-kind split didn't apply"
        )

    @pytest.mark.asyncio
    async def test_chat_kind_default_is_ad_hoc(self, test_engine):
        cols = await _columns(test_engine, "chat")
        kind = cols["kind"]
        default = (kind.get("default") or "").lower()
        # Existing chats become ad_hoc by default — no backfill confusion.
        assert "ad_hoc" in default, (
            f"chat.kind must default to 'ad_hoc'; got {default!r}"
        )

    @pytest.mark.asyncio
    async def test_chat_has_dashboard_id_column(self, test_engine):
        cols = await _columns(test_engine, "chat")
        assert "dashboard_id" in cols, (
            "chat.dashboard_id column missing — needed for the chat ↔ "
            "dashboard back-pointer (build threads)"
        )

    @pytest.mark.asyncio
    async def test_chat_dashboard_id_is_nullable(self, test_engine):
        cols = await _columns(test_engine, "chat")
        # Only build chats (kind=dashboard_build) point at a dashboard.
        # ad_hoc chats leave it NULL.
        assert cols["dashboard_id"]["nullable"] is True, (
            "chat.dashboard_id must be nullable — ad_hoc chats don't have "
            "a dashboard"
        )

    @pytest.mark.asyncio
    async def test_chat_dashboard_fk_cascades(self, test_engine):
        # When a dashboard is deleted, its build-chat is deleted too.
        # Mirror of the dashboard → chat FK we set up the other way.
        fks = await _foreign_keys(test_engine, "chat")
        dash_fk = next(
            (fk for fk in fks if fk["referred_table"] == "dashboard"), None
        )
        assert dash_fk is not None, (
            "chat → dashboard FK missing"
        )
        assert _ondelete(dash_fk) == "CASCADE", (
            f"chat.dashboard_id ondelete must be CASCADE; got "
            f"{_ondelete(dash_fk)!r}"
        )
