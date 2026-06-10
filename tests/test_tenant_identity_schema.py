"""
Schema test for the NEU-X4 tenant-identity columns.

NEU-X4 decouples tenant identity from email domain. Two changes
matter at the schema level:

  1. ``tenant.name`` already exists and stays — but its semantics
     change from "email-domain-derived label" to "free-text
     organization name set by the Owner during onboarding." No
     migration needed for the column itself; the change is in how
     callers populate it.

  2. ``tenant.allowed_invitation_domains`` (new) — TEXT[] NOT NULL
     DEFAULT '{}'. Empty list means "no restriction" (anyone with a
     valid email can be invited). Owner adds entries via Settings
     to enforce a domain allowlist (Slack-style).

This file pins the new column's existence + the empty-default
behavior. Without the empty default, every existing tenant would
suddenly be locked into an empty allowlist (= can't invite anyone).
The migration backfills the default and the column carries it
forward for new tenants.

See ``user-stories/tenant-admin-actions.md`` § (future) "Settings"
for the product spec — to be written as part of this slice.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker

from neutrino_database.models.enums import TenantStatusEnum
from neutrino_database.models.orm import Tenant


def _unique() -> str:
    return uuid.uuid4().hex[:12]


class TestTenantAllowedInvitationDomains:
    @pytest.mark.asyncio
    async def test_allowed_invitation_domains_column_exists(self, test_engine):
        """The column must exist, be TEXT[], NOT NULL, default empty."""
        async with test_engine.connect() as conn:
            cols = await conn.run_sync(
                lambda sync_conn: {
                    c["name"]: c
                    for c in sa.inspect(sync_conn).get_columns("tenant")
                }
            )
        assert "allowed_invitation_domains" in cols, (
            "tenant.allowed_invitation_domains is required for the "
            "Owner-controlled domain allowlist (NEU-X4)."
        )
        col = cols["allowed_invitation_domains"]
        assert col["nullable"] is False, (
            "allowed_invitation_domains must be NOT NULL — empty list "
            "means 'no restriction', NULL would be ambiguous."
        )
        # ARRAY of TEXT — the inspector reports the underlying ARRAY type.
        # Just verify it's recognized as ARRAY-shape; the element type
        # is a Postgres-specific check.
        col_type = col["type"]
        assert isinstance(col_type, sa.dialects.postgresql.ARRAY), (
            f"Expected ARRAY column; got {col_type!r}"
        )

    @pytest.mark.asyncio
    async def test_new_tenant_inherits_empty_allowlist(self, test_engine):
        """A new tenant created without specifying
        allowed_invitation_domains lands an empty list — i.e. "no
        restriction" — not NULL and not a sentinel value."""
        SessionMaker = async_sessionmaker(bind=test_engine, expire_on_commit=False)
        suffix = _unique()
        tenant_id = str(uuid.uuid4())

        try:
            async with SessionMaker() as setup:
                async with setup.begin():
                    setup.add(
                        Tenant(
                            id=tenant_id,
                            name=f"Acme-{suffix}",
                            org_external_id=f"org-{suffix}",
                            status=TenantStatusEnum.ACTIVE,
                            created_at=datetime.now(UTC),
                            updated_at=datetime.now(UTC),
                        )
                    )

            async with SessionMaker() as verify:
                fetched = await verify.get(Tenant, tenant_id)
                assert fetched is not None
                assert fetched.allowed_invitation_domains == [], (
                    "Default must be empty list (no restriction); "
                    f"got {fetched.allowed_invitation_domains!r}"
                )
        finally:
            async with SessionMaker() as cleanup:
                async with cleanup.begin():
                    await cleanup.execute(
                        sa.delete(Tenant).where(Tenant.id == tenant_id)
                    )

    @pytest.mark.asyncio
    async def test_can_set_and_round_trip_allowed_domains(self, test_engine):
        """Setting a multi-domain allowlist round-trips through the ORM."""
        SessionMaker = async_sessionmaker(bind=test_engine, expire_on_commit=False)
        suffix = _unique()
        tenant_id = str(uuid.uuid4())

        try:
            async with SessionMaker() as setup:
                async with setup.begin():
                    setup.add(
                        Tenant(
                            id=tenant_id,
                            name=f"IBM-{suffix}",
                            org_external_id=f"ibm-{suffix}",
                            status=TenantStatusEnum.ACTIVE,
                            allowed_invitation_domains=[
                                "ibm.com",
                                "ibm.co.in",
                                "ibm.co.uk",
                            ],
                            created_at=datetime.now(UTC),
                            updated_at=datetime.now(UTC),
                        )
                    )

            async with SessionMaker() as verify:
                fetched = await verify.get(Tenant, tenant_id)
                assert fetched is not None
                assert sorted(fetched.allowed_invitation_domains) == [
                    "ibm.co.in",
                    "ibm.co.uk",
                    "ibm.com",
                ]
        finally:
            async with SessionMaker() as cleanup:
                async with cleanup.begin():
                    await cleanup.execute(
                        sa.delete(Tenant).where(Tenant.id == tenant_id)
                    )
