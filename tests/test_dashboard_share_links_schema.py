"""
Schema tests for the share-link upgrade on ``dashboard_link_token``
(NEU-1811 DA-P3.4).

DA-P3.1 shipped a v1 ``dashboard_link_token`` table sufficient for
"mint a token and look it up." DA-P3.4 hardens that table to the
production-grade share-link pattern mature systems converge on
(Stripe / GitHub PAT / Notion link-share):

  * Tokens stored as **hashes**, not plaintext. A DB read must not
    yield active link credentials. We store SHA-256 of the URL-safe
    token; the mint path is the only place the plaintext ever
    materialises (and is returned to the caller exactly once).
  * A short prefix (``token_short``, first 8 chars) is kept in the
    clear for UI identification — curators see "link · xK4f2nM9"
    in the share dialog without exposing the secret. Same pattern
    GitHub uses for PAT listings.
  * Audit of *who* revoked, not just *when*. ``revoked_by_user_id``
    closes the audit-trail gap from DA-P3.1.
  * A partial index that exactly matches the "active link?" predicate
    powers the Library's Shared-pill LEFT JOIN without bloating the
    index on revoked / expired rows.

This file pins the upgraded shape. Tests fail before the migration +
``tables.py`` change land; pass after. The pre-existing
``TestDashboardLinkTokenTable`` class in ``test_dashboard_schema.py``
is updated in the same commit (rename ``token`` → ``token_hash`` in
its expected-columns set; the other assertions there still apply).
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa


# ---------------------------------------------------------------------------
# Helpers — keep aligned with test_dashboard_schema.py
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


async def _check_constraints(test_engine, table_name: str) -> list[dict]:
    async with test_engine.connect() as conn:
        return await conn.run_sync(
            lambda sync_conn: sa.inspect(sync_conn).get_check_constraints(
                table_name
            )
        )


async def _partial_index_predicates(
    test_engine, table_name: str
) -> dict[str, str]:
    """Returns {index_name: WHERE clause text} for partial indexes.

    SQLAlchemy reflection surfaces partial-index predicates
    inconsistently across driver versions; query ``pg_indexes``
    directly for a reliable read.
    """
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
            # indexdef is the full CREATE INDEX statement; the partial
            # predicate (if any) is the trailing ``WHERE ...`` clause.
            upper = indexdef.upper()
            where_pos = upper.rfind(" WHERE ")
            if where_pos >= 0:
                out[name] = indexdef[where_pos + len(" WHERE ") :].strip()
        return out


def _ondelete(fk: dict) -> str | None:
    return (fk.get("options") or {}).get("ondelete")


# ---------------------------------------------------------------------------
# Token storage — plaintext → hash
# ---------------------------------------------------------------------------


class TestTokenHashStorage:
    """v1 stored the URL-safe token in plaintext. DA-P3.4 hashes
    it at rest so a DB read doesn't yield active link credentials —
    the Stripe API-key / GitHub PAT model. The original ``token``
    column must go away in the same migration so no caller can
    accidentally read or write plaintext."""

    @pytest.mark.asyncio
    async def test_token_hash_column_present(self, test_engine):
        cols = await _columns(test_engine, "dashboard_link_token")
        assert "token_hash" in cols, (
            "token_hash column missing — DA-P3.4 stores SHA-256 of the "
            "URL-safe token, not the plaintext. Plaintext lives only in "
            "the response of the mint endpoint."
        )

    @pytest.mark.asyncio
    async def test_token_hash_not_nullable(self, test_engine):
        cols = await _columns(test_engine, "dashboard_link_token")
        assert cols["token_hash"]["nullable"] is False, (
            "token_hash must be NOT NULL — a row without a hash is "
            "an unreachable token, never a valid state."
        )

    @pytest.mark.asyncio
    async def test_old_token_column_gone(self, test_engine):
        cols = await _columns(test_engine, "dashboard_link_token")
        assert "token" not in cols, (
            "Old plaintext ``token`` column must be dropped in DA-P3.4 — "
            "leaving it creates a confusion surface (which field is "
            "authoritative?) and a leak surface (mistakes in service "
            "code could still write plaintext)."
        )

    @pytest.mark.asyncio
    async def test_token_hash_unique_index(self, test_engine):
        # Hash collisions are cryptographically improbable for SHA-256,
        # but uniqueness at the index level is still required: the
        # resolve path keys off it, and a duplicate would surface as
        # a multi-row read at lookup. UNIQUE makes the impossibility
        # explicit in the schema.
        indexes = await _indexes(test_engine, "dashboard_link_token")
        hash_idx = next(
            (i for i in indexes if i["column_names"] == ["token_hash"]),
            None,
        )
        assert hash_idx is not None, (
            "Need a unique index on token_hash — the public viewer "
            "route's resolve step keys off it."
        )
        assert hash_idx.get("unique") is True, (
            "token_hash index must be UNIQUE."
        )


# ---------------------------------------------------------------------------
# Token-short — UI identifier
# ---------------------------------------------------------------------------


class TestTokenShort:
    """The share dialog needs to show curators which links are which
    without exposing the secret. ``token_short`` carries the first 8
    chars of the URL-safe plaintext (set once at mint, never updated)
    for human identification — same idea as GitHub PAT listings
    showing ``ghp_xxxxXXXX``."""

    @pytest.mark.asyncio
    async def test_token_short_column_present(self, test_engine):
        cols = await _columns(test_engine, "dashboard_link_token")
        assert "token_short" in cols, (
            "token_short column missing — needed for the share dialog "
            "to identify links without exposing the secret."
        )

    @pytest.mark.asyncio
    async def test_token_short_not_nullable(self, test_engine):
        cols = await _columns(test_engine, "dashboard_link_token")
        assert cols["token_short"]["nullable"] is False, (
            "token_short is set at mint time alongside token_hash — "
            "NOT NULL keeps the invariant explicit."
        )


# ---------------------------------------------------------------------------
# Revoker audit
# ---------------------------------------------------------------------------


class TestRevokerAudit:
    """DA-P3.1 carried ``revoked_at`` (when) but not ``revoked_by``
    (who). For SOC 2 / compliance the audit trail must answer both
    — and the audit_log row that emits on revoke references the
    user via this FK."""

    @pytest.mark.asyncio
    async def test_revoked_by_user_id_column_present(self, test_engine):
        cols = await _columns(test_engine, "dashboard_link_token")
        assert "revoked_by_user_id" in cols, (
            "revoked_by_user_id missing — audit trail for share-link "
            "revoke must record both timestamp AND actor."
        )

    @pytest.mark.asyncio
    async def test_revoked_by_user_id_nullable(self, test_engine):
        # Nullable: pre-revoke rows have no revoker; system-initiated
        # revokes (future bg-job sweeper) may also leave it NULL.
        cols = await _columns(test_engine, "dashboard_link_token")
        assert cols["revoked_by_user_id"]["nullable"] is True, (
            "revoked_by_user_id is NULL for un-revoked rows."
        )

    @pytest.mark.asyncio
    async def test_revoked_by_user_id_fk_set_null(self, test_engine):
        fks = await _foreign_keys(test_engine, "dashboard_link_token")
        revoker_fk = next(
            (
                fk
                for fk in fks
                if fk["constrained_columns"] == ["revoked_by_user_id"]
            ),
            None,
        )
        assert revoker_fk is not None, (
            "revoked_by_user_id needs a FK to user(id)."
        )
        assert revoker_fk["referred_table"] == "user"
        assert _ondelete(revoker_fk) == "SET NULL", (
            "Deleting the revoker user must NOT cascade-delete the "
            "share-link row — the audit fact (this link was revoked "
            "at T) outlives the actor."
        )


# ---------------------------------------------------------------------------
# Partial index for the active-link lookup
# ---------------------------------------------------------------------------


class TestActiveLinkPartialIndex:
    """The Library list query joins dashboards with their active
    share links to power the "Shared · N links" pill. The full query
    predicate is ``revoked_at IS NULL AND (expires_at IS NULL OR
    expires_at > now())`` — but Postgres rejects ``now()`` (STABLE,
    not IMMUTABLE) inside an index predicate, so the partial index
    filters on the immutable half (``revoked_at IS NULL``) and the
    query layer applies the ``expires_at`` residual at scan time.
    Standard share-link pattern — Stripe API keys + GitHub PATs
    index this way."""

    @pytest.mark.asyncio
    async def test_active_link_partial_index_exists(self, test_engine):
        partials = await _partial_index_predicates(
            test_engine, "dashboard_link_token"
        )
        # Assert by predicate rather than name to keep the test
        # resilient to migration-name churn. Required: a partial
        # index whose WHERE clause filters on ``revoked_at IS NULL``.
        matching = [
            (name, where)
            for name, where in partials.items()
            if "revoked_at" in where.lower()
        ]
        assert matching, (
            "No partial index on dashboard_link_token filtering on "
            "revoked_at IS NULL. Expected: "
            "(dashboard_id) WHERE revoked_at IS NULL. "
            f"Got partial indexes: {partials!r}"
        )

    @pytest.mark.asyncio
    async def test_old_plain_dashboard_index_dropped(self, test_engine):
        # The old ix_dashboard_link_token_dashboard was a non-partial
        # index on dashboard_id covering ALL rows including revoked /
        # expired. The partial index above strictly subsumes its
        # query patterns; keeping both wastes disk + write cost on
        # every mint / revoke.
        indexes = await _indexes(test_engine, "dashboard_link_token")
        plain = next(
            (
                i
                for i in indexes
                if i.get("name") == "ix_dashboard_link_token_dashboard"
            ),
            None,
        )
        # If the old index is gone OR is itself the partial one, fine.
        if plain is not None:
            partials = await _partial_index_predicates(
                test_engine, "dashboard_link_token"
            )
            assert plain.get("name") in partials, (
                "Old non-partial index ix_dashboard_link_token_dashboard "
                "should be dropped in DA-P3.4 — the active-link partial "
                "index covers the queries that referenced it."
            )


# ---------------------------------------------------------------------------
# Check constraints — temporal invariants
# ---------------------------------------------------------------------------


class TestTemporalCheckConstraints:
    """Two cheap CHECK constraints close the gap between "the service
    layer never writes these states" (current guarantee) and "the
    schema rejects these states" (production-grade). They cost
    nothing at write time and turn a class of service-bug into a
    DB-level constraint error."""

    @pytest.mark.asyncio
    async def test_expires_at_after_created_at(self, test_engine):
        checks = await _check_constraints(test_engine, "dashboard_link_token")
        # Look for any CHECK referencing both expires_at and created_at
        # — name is set by the migration and asserted by predicate
        # text so renames don't break the test.
        matching = [
            c
            for c in checks
            if "expires_at" in (c.get("sqltext") or "")
            and "created_at" in (c.get("sqltext") or "")
        ]
        assert matching, (
            "Missing CHECK (expires_at IS NULL OR expires_at > "
            "created_at). A row with expires_at <= created_at is born "
            "already-expired — schema should reject it."
        )

    @pytest.mark.asyncio
    async def test_revoked_at_at_or_after_created_at(self, test_engine):
        checks = await _check_constraints(test_engine, "dashboard_link_token")
        matching = [
            c
            for c in checks
            if "revoked_at" in (c.get("sqltext") or "")
            and "created_at" in (c.get("sqltext") or "")
        ]
        assert matching, (
            "Missing CHECK (revoked_at IS NULL OR revoked_at >= "
            "created_at). A row revoked before it was created is "
            "incoherent."
        )
