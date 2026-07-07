"""
NC-151 (Slice B, B1) — the polymorphic ``share_link`` table.

The share feature: mint a link to a resource that a recipient opens — Public
(anyone) or Private (workspace members with the link). Rather than a per-type
copy of DA's ``dashboard_link_token``, this is ONE sharing subsystem keyed by
``(resource_type, resource_id)`` — chat_artifact today, dashboards/others later.

Improves on DA's dashboard sharing (which this supersedes long-term):
  * ``visibility`` (public | workspace) — DA links are all-or-nothing public;
    ours support workspace-members-only-with-link too.
  * polymorphic ``resource_type`` + ``resource_id`` — one audited token stack.
  * ``label`` — a curator-facing name so many links stay distinguishable.
  * ``last_accessed_at`` alongside ``accessed_count``.
Keeps DA's good hardening: SHA-256 ``token_hash`` (UNIQUE), non-secret
``token_short`` prefix, optional ``expires_at``, soft-delete ``revoked_at`` +
``revoked_by``, CHECK constraints, partial active-link index.

Note: ``resource_id`` is deliberately NOT a FK — it points at different tables by
``resource_type``. The service validates the target on mint/resolve.

Schema is built from ``tables.py`` via ``metadata.create_all`` (conftest); the
migration is required separately for dev/prod.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa


async def _columns(test_engine, table_name: str) -> dict:
    async with test_engine.connect() as conn:
        return await conn.run_sync(
            lambda sync_conn: {
                c["name"]: c for c in sa.inspect(sync_conn).get_columns(table_name)
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


async def _udt_names(test_engine, table_name: str) -> dict[str, str]:
    async with test_engine.connect() as conn:
        result = await conn.execute(
            sa.text(
                "SELECT column_name, udt_name FROM information_schema.columns "
                "WHERE table_name = :t"
            ),
            {"t": table_name},
        )
        return {name: udt for name, udt in result.fetchall()}


def _ondelete(fk: dict) -> str | None:
    return (fk.get("options") or {}).get("ondelete")


def _fk_for(fks: list[dict], column: str) -> dict | None:
    return next((fk for fk in fks if fk["constrained_columns"] == [column]), None)


class TestShareLinkColumns:
    @pytest.mark.asyncio
    async def test_core_columns_exist(self, test_engine):
        cols = await _columns(test_engine, "share_link")
        expected = {
            "id", "tenant_id", "workspace_id", "resource_type", "resource_id",
            "visibility", "token_hash", "token_short", "label", "created_by",
            "expires_at", "revoked_at", "revoked_by", "accessed_count",
            "last_accessed_at", "created_at", "updated_at",
        }
        missing = expected - set(cols.keys())
        assert not missing, f"share_link missing {sorted(missing)}. Have {sorted(cols)}"

    @pytest.mark.asyncio
    async def test_resource_type_and_visibility_are_native_enums(self, test_engine):
        udts = await _udt_names(test_engine, "share_link")
        assert udts.get("resource_type") == "share_link_resource_type"
        assert udts.get("visibility") == "share_link_visibility"

    @pytest.mark.asyncio
    async def test_visibility_defaults_to_workspace(self, test_engine):
        """Private-first: a new link is workspace-only unless explicitly made
        public — the safe default for a snapshot that may carry restricted data."""
        cols = await _columns(test_engine, "share_link")
        assert cols["visibility"]["nullable"] is False
        assert "workspace" in (cols["visibility"].get("default") or "")

    @pytest.mark.asyncio
    async def test_resource_id_not_null_and_not_a_fk(self, test_engine):
        cols = await _columns(test_engine, "share_link")
        assert cols["resource_id"]["nullable"] is False
        fks = await _foreign_keys(test_engine, "share_link")
        assert _fk_for(fks, "resource_id") is None, (
            "resource_id is polymorphic — it must NOT be a FK to one table."
        )

    @pytest.mark.asyncio
    async def test_token_hash_not_null(self, test_engine):
        cols = await _columns(test_engine, "share_link")
        assert cols["token_hash"]["nullable"] is False

    @pytest.mark.asyncio
    async def test_accessed_count_defaults_zero(self, test_engine):
        cols = await _columns(test_engine, "share_link")
        assert cols["accessed_count"]["nullable"] is False
        assert "0" in (cols["accessed_count"].get("default") or "")


class TestShareLinkForeignKeys:
    @pytest.mark.asyncio
    async def test_tenant_and_workspace_cascade(self, test_engine):
        fks = await _foreign_keys(test_engine, "share_link")
        for col, ref in (("tenant_id", "tenant"), ("workspace_id", "workspace")):
            fk = _fk_for(fks, col)
            assert fk and fk["referred_table"] == ref
            assert _ondelete(fk) == "CASCADE"

    @pytest.mark.asyncio
    async def test_created_by_and_revoked_by_set_null(self, test_engine):
        fks = await _foreign_keys(test_engine, "share_link")
        for col in ("created_by", "revoked_by"):
            fk = _fk_for(fks, col)
            assert fk and fk["referred_table"] == "user"
            assert _ondelete(fk) == "SET NULL", (
                f"share_link.{col} must SET NULL — a departed user must not "
                f"cascade-delete the audit trail of who created/revoked a link."
            )


class TestShareLinkIndexes:
    @pytest.mark.asyncio
    async def test_token_hash_unique(self, test_engine):
        indexes = await _indexes(test_engine, "share_link")
        assert any(
            ix.get("unique") and ix["column_names"] == ["token_hash"]
            for ix in indexes
        ), "token_hash needs a UNIQUE index (single-row resolve lookup)."

    @pytest.mark.asyncio
    async def test_active_links_partial_index_on_resource(self, test_engine):
        """Listing a resource's active links: WHERE resource_type/id AND
        revoked_at IS NULL — partial so revoked history doesn't bloat it."""
        async with test_engine.connect() as conn:
            rows = await conn.execute(
                sa.text(
                    "SELECT indexdef FROM pg_indexes WHERE tablename = 'share_link'"
                )
            )
            defs = [r[0] for r in rows.fetchall()]
        has = any("resource_id" in d and "revoked_at" in d.lower() for d in defs)
        assert has, f"share_link needs a partial active-link index. Got: {defs}"
