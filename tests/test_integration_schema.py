"""
WF-VS1.1 — Unified integration hierarchy schema.

Schema-shape tests for the three tables that back the workflow pillar's
connector hierarchy (and, in later slices, ES + DA once they migrate
onto this model):

  * ``integration`` — the universal credential record. ONE row per
    credential, established once at the tenant level (or owned by a
    user for the personal tier). The Vault secret lives behind
    ``vault_secret_id``; the row itself never carries the secret.
  * ``integration_workspace_enablement`` — per-workspace opt-in for a
    tenant integration, with per-workspace capability scope-down.
  * ``integration_member_grant`` — per-member ACL (deny-wins), the
    same cardinality/shape as workspace_da_access_grant.

Locked semantics (PRD product-feature-roadmap/workflow-execution §5a, §9):

  * ``owner_kind`` is exactly ``tenant`` | ``user``. There is no
    workspace-owned tier — even a single-workspace tenant defines at
    the tenant level and the workspace enables. The CHECK constraint
    enforces the invariant:
        tenant → owner_user_id IS NULL  AND workspace_id IS NULL
        user   → owner_user_id NOT NULL AND workspace_id NOT NULL
  * ``identity_kind`` (user | app | service_account) is who the
    destination SaaS sees; derived from the provider catalog at
    create time, never client-supplied.
  * ``capabilities`` is the cross-pillar axis: ES reads via 'ingest',
    DA via 'query', WF via 'act'. One integration, many consumers.
  * A tenant can't connect the same provider account twice:
    UNIQUE (tenant_id, provider, external_account_id).
  * Enablement scopes capabilities DOWN (a subset of the integration's
    capabilities); enforced in the service, the column just stores it.

This file pins the schema shape. Tests fail before the migration +
``tables.py`` change land; pass after.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa


# ---------------------------------------------------------------------------
# Helpers (parity with test_workspace_da_access_grant_schema.py)
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


async def _check_constraints(test_engine, table_name: str) -> list[dict]:
    async with test_engine.connect() as conn:
        return await conn.run_sync(
            lambda sync_conn: sa.inspect(sync_conn).get_check_constraints(
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
# integration — column shape
# ---------------------------------------------------------------------------


class TestIntegrationColumns:
    @pytest.mark.asyncio
    async def test_required_columns_present(self, test_engine):
        cols = await _columns(test_engine, "integration")
        expected = {
            "id",
            "tenant_id",
            "owner_kind",
            "owner_user_id",
            "workspace_id",
            "provider",
            "display_name",
            "vault_secret_id",
            "identity_kind",
            "identity_label",
            "auth_kind",
            "oauth_scopes_granted",
            "instance_url",
            "external_account_id",
            "external_account_name",
            "capabilities",
            "status",
            "last_verified_at",
            "metadata",
            "created_by",
            "created_at",
            "updated_at",
        }
        missing = expected - set(cols.keys())
        assert not missing, (
            f"integration missing columns: {missing}. "
            f"Got: {sorted(cols.keys())}"
        )

    @pytest.mark.asyncio
    async def test_not_null_columns(self, test_engine):
        cols = await _columns(test_engine, "integration")
        # The columns that must always be present to make the row
        # meaningful: who owns it (tenant), what it is, how it auths,
        # what it can do, its lifecycle.
        #
        # UC-ES-DB-1.A relaxed vault_secret_id to NULLABLE so local-only
        # sources (auth_kind='none', e.g. member uploads a PDF) can sit
        # on this table without a placeholder secret. The NULLABLE check
        # for vault_secret_id lives below in
        # ``test_vault_secret_id_is_nullable``.
        for non_null in (
            "tenant_id",
            "owner_kind",
            "provider",
            "display_name",
            "identity_kind",
            "auth_kind",
            "capabilities",
            "status",
            "created_by",
        ):
            assert cols[non_null]["nullable"] is False, (
                f"{non_null} must be NOT NULL on integration"
            )

    @pytest.mark.asyncio
    async def test_vault_secret_id_is_nullable(self, test_engine):
        """UC-ES-DB-1.A — vault_secret_id is NULLABLE so auth_kind='none'
        rows (local upload sources) can omit the secret pointer."""
        cols = await _columns(test_engine, "integration")
        assert cols["vault_secret_id"]["nullable"] is True, (
            "vault_secret_id must be NULLABLE after UC-ES-DB-1.A — see "
            "alembic e2f3a4b5c6d7."
        )

    @pytest.mark.asyncio
    async def test_owner_user_id_and_workspace_id_nullable(self, test_engine):
        """Both are NULL for tenant integrations, set for personal —
        so the columns themselves must be nullable; the CHECK
        constraint enforces the per-owner_kind invariant."""
        cols = await _columns(test_engine, "integration")
        assert cols["owner_user_id"]["nullable"] is True
        assert cols["workspace_id"]["nullable"] is True

    @pytest.mark.asyncio
    async def test_no_credential_columns_on_base_table(self, test_engine):
        """Credentials live in Vault, never in the integration row.
        Guard against anyone adding a secret/token/password column."""
        cols = await _columns(test_engine, "integration")
        forbidden = [
            c
            for c in cols
            if any(
                bad in c.lower()
                for bad in ("secret", "token", "password", "credential")
            )
            and c != "vault_secret_id"  # the pointer is allowed
        ]
        assert not forbidden, (
            f"integration must not carry credential columns: {forbidden}. "
            "Secrets belong in Vault behind vault_secret_id only."
        )


# ---------------------------------------------------------------------------
# integration — enum types
# ---------------------------------------------------------------------------


class TestIntegrationEnums:
    @pytest.mark.asyncio
    async def test_owner_kind_enum_values(self, test_engine):
        values = await _enum_values(test_engine, "integration_owner_kind")
        assert set(values) == {"tenant", "user", "workspace"}, (
            "integration_owner_kind must be tenant|user|workspace — "
            "'workspace' is the workspace-owned tier (a workspace admin "
            "establishes a connection their workspace owns). "
            f"Got {values}"
        )

    @pytest.mark.asyncio
    async def test_identity_kind_enum_values(self, test_engine):
        values = await _enum_values(test_engine, "integration_identity_kind")
        # 'none' added in UC-ES-DB-1.A for local upload sources where
        # there is no remote destination → no identity it would see.
        assert set(values) == {"user", "app", "service_account", "none"}, (
            "integration_identity_kind must be user|app|service_account|none; "
            f"got {values}"
        )

    @pytest.mark.asyncio
    async def test_auth_kind_enum_values(self, test_engine):
        values = await _enum_values(test_engine, "integration_auth_kind")
        # 'none' added in UC-ES-DB-1.A for sources that don't
        # authenticate against a remote system (member-uploaded files).
        assert set(values) == {"oauth2", "api_key", "basic", "custom", "none"}, (
            "integration_auth_kind must be oauth2|api_key|basic|custom|none; "
            f"got {values}"
        )

    @pytest.mark.asyncio
    async def test_status_enum_values(self, test_engine):
        values = await _enum_values(test_engine, "integration_status")
        assert set(values) == {"active", "disabled", "revoked", "expired"}, (
            "integration_status must be active|disabled|revoked|expired; "
            f"got {values}"
        )


# ---------------------------------------------------------------------------
# integration — owner_kind invariant (the load-bearing CHECK)
# ---------------------------------------------------------------------------


class TestIntegrationOwnerKindInvariant:
    @pytest.mark.asyncio
    async def test_owner_kind_check_constraint_exists(self, test_engine):
        """tenant → (owner_user_id NULL, workspace_id NULL);
        user   → (owner_user_id NOT NULL, workspace_id NOT NULL).
        Pinned as a CHECK so the DB refuses an ambiguous row."""
        checks = await _check_constraints(test_engine, "integration")
        blob = " ".join((c.get("sqltext") or "") for c in checks).lower()
        assert "owner_kind" in blob and "owner_user_id" in blob, (
            "Expected a CHECK constraint tying owner_kind to "
            "owner_user_id / workspace_id nullability. Existing checks: "
            f"{[c.get('name') for c in checks]}"
        )


# ---------------------------------------------------------------------------
# integration — FK + cascade behaviour
# ---------------------------------------------------------------------------


class TestIntegrationForeignKeys:
    @pytest.mark.asyncio
    async def test_tenant_id_cascade(self, test_engine):
        fks = await _foreign_keys(test_engine, "integration")
        fk = next(
            (f for f in fks if f["constrained_columns"] == ["tenant_id"]),
            None,
        )
        assert fk is not None and fk["referred_table"] == "tenant"
        assert _ondelete(fk) == "CASCADE", (
            "tenant_id ondelete must be CASCADE — deleting a tenant "
            "purges its integrations."
        )

    @pytest.mark.asyncio
    async def test_owner_user_id_cascade(self, test_engine):
        fks = await _foreign_keys(test_engine, "integration")
        fk = next(
            (f for f in fks if f["constrained_columns"] == ["owner_user_id"]),
            None,
        )
        assert fk is not None and fk["referred_table"] == "user"
        assert _ondelete(fk) == "CASCADE", (
            "owner_user_id ondelete must be CASCADE — offboarding a user "
            "purges their personal integrations."
        )

    @pytest.mark.asyncio
    async def test_workspace_id_cascade(self, test_engine):
        fks = await _foreign_keys(test_engine, "integration")
        fk = next(
            (f for f in fks if f["constrained_columns"] == ["workspace_id"]),
            None,
        )
        assert fk is not None and fk["referred_table"] == "workspace"
        assert _ondelete(fk) == "CASCADE"


# ---------------------------------------------------------------------------
# integration — uniqueness (no duplicate provider account per tenant)
# ---------------------------------------------------------------------------


class TestIntegrationUniqueness:
    @pytest.mark.asyncio
    async def test_unique_tenant_provider_account(self, test_engine):
        ucs = await _unique_constraints(test_engine, "integration")
        match = [
            uc
            for uc in ucs
            if set(uc["column_names"])
            == {"tenant_id", "provider", "external_account_id"}
        ]
        assert match, (
            "Expected UNIQUE (tenant_id, provider, external_account_id) — "
            "a tenant can't connect the same provider account twice."
        )


# ---------------------------------------------------------------------------
# integration_workspace_enablement — per-workspace opt-in
# ---------------------------------------------------------------------------


class TestIntegrationWorkspaceEnablement:
    @pytest.mark.asyncio
    async def test_required_columns_present(self, test_engine):
        cols = await _columns(
            test_engine, "integration_workspace_enablement"
        )
        expected = {
            "id",
            "integration_id",
            "workspace_id",
            "capabilities_enabled",
            "display_name_override",
            "status",
            "enabled_by",
            "enabled_at",
        }
        missing = expected - set(cols.keys())
        assert not missing, (
            f"integration_workspace_enablement missing: {missing}. "
            f"Got: {sorted(cols.keys())}"
        )

    @pytest.mark.asyncio
    async def test_integration_id_cascade(self, test_engine):
        fks = await _foreign_keys(
            test_engine, "integration_workspace_enablement"
        )
        fk = next(
            (
                f
                for f in fks
                if f["constrained_columns"] == ["integration_id"]
            ),
            None,
        )
        assert fk is not None and fk["referred_table"] == "integration"
        assert _ondelete(fk) == "CASCADE", (
            "Deleting the tenant integration must purge its workspace "
            "enablements."
        )

    @pytest.mark.asyncio
    async def test_one_enablement_per_workspace(self, test_engine):
        ucs = await _unique_constraints(
            test_engine, "integration_workspace_enablement"
        )
        match = [
            uc
            for uc in ucs
            if set(uc["column_names"]) == {"integration_id", "workspace_id"}
        ]
        assert match, (
            "Expected UNIQUE (integration_id, workspace_id) — a workspace "
            "enables a given tenant integration at most once."
        )


# ---------------------------------------------------------------------------
# integration_member_grant — per-member ACL (deny-wins)
# ---------------------------------------------------------------------------


class TestIntegrationMemberGrant:
    @pytest.mark.asyncio
    async def test_required_columns_present(self, test_engine):
        cols = await _columns(test_engine, "integration_member_grant")
        expected = {
            "id",
            "workspace_id",
            "user_id",
            "integration_id",
            "capability",
            "effect",
            "created_by",
            "created_at",
        }
        missing = expected - set(cols.keys())
        assert not missing, (
            f"integration_member_grant missing: {missing}. "
            f"Got: {sorted(cols.keys())}"
        )

    @pytest.mark.asyncio
    async def test_effect_enum_reused(self, test_engine):
        """Reuses the same allow|deny effect semantics as DA ACL.
        Deny-wins-anywhere is encoded in the resolver, not the schema."""
        cols = await _columns(test_engine, "integration_member_grant")
        assert "effect" in cols

    @pytest.mark.asyncio
    async def test_one_grant_per_member_integration_capability(
        self, test_engine
    ):
        ucs = await _unique_constraints(
            test_engine, "integration_member_grant"
        )
        match = [
            uc
            for uc in ucs
            if set(uc["column_names"])
            == {"workspace_id", "user_id", "integration_id", "capability"}
        ]
        assert match, (
            "Expected UNIQUE (workspace_id, user_id, integration_id, "
            "capability) — one effect per member per integration per "
            "capability."
        )

    @pytest.mark.asyncio
    async def test_integration_id_cascade(self, test_engine):
        fks = await _foreign_keys(test_engine, "integration_member_grant")
        fk = next(
            (
                f
                for f in fks
                if f["constrained_columns"] == ["integration_id"]
            ),
            None,
        )
        assert fk is not None and fk["referred_table"] == "integration"
        assert _ondelete(fk) == "CASCADE"
