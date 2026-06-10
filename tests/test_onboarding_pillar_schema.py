"""
Schema tests for the onboarding-completion + multi-select-pillars
slice (Slice 1A wizard prerequisites).

Two new schema surfaces land together:

  1. ``tenant.onboarding_completed_at`` — a first-class TIMESTAMPTZ
     column that replaces the ``!workspace_id`` proxy currently used
     by the FE post-auth callback to decide ``/welcome`` vs ``/chat``.
     The wizard's last step stamps this column atomically.

  2. ``workspace.enabled_pillars`` — a NOT NULL array of the new
     ``pillar`` enum (``ENTERPRISE_SEARCH`` | ``DATA_ANALYTICS`` |
     ``WORKFLOW_EXECUTION``). Replaces the conflated single-value
     ``orchestrator_config.router_mode`` enum with a real multi-select.
     ``router_mode`` itself stays during a transition window — the
     gateway will write both, agent-platform continues to read
     ``router_mode``, and a later cleanup migration removes it once
     downstream consumers have caught up.

Both are added in the same alembic migration on branch ``NEU-1801``.
These tests pin the schema after ``Base.metadata.create_all`` brings
the test DB up to the canonical ``tables.py``. They are written
*before* the schema change (TDD discipline) so they fail loudly and
force the change in ``tables.py`` + ``orm.py`` + the migration to
match each other.

See ``user-stories/tenant-onboarding.md`` (locked decisions §1, §3)
and ``our-engineering-standards.md`` §10 (migration discipline) for
context.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker

from neutrino_database.models.enums import (
    TenantStatusEnum,
    WorkspaceStatusEnum,
)
from neutrino_database.models.orm import Tenant, Workspace


def _unique() -> str:
    return uuid.uuid4().hex[:12]


class TestTenantOnboardingColumn:
    """Tenant gains a first-class onboarding-completion timestamp."""

    @pytest.mark.asyncio
    async def test_tenant_table_has_onboarding_completed_at_column(self, test_engine):
        """
        After Base.metadata.create_all, the `tenant` table must include
        an `onboarding_completed_at` column. Asserted via SQLAlchemy
        reflection so we catch tables.py and the migration drifting —
        both must change together (the migration creates it on real DBs;
        tables.py creates it via metadata for tests).
        """
        async with test_engine.connect() as conn:
            cols = await conn.run_sync(
                lambda sync_conn: {
                    c["name"]: c
                    for c in sa.inspect(sync_conn).get_columns("tenant")
                }
            )
        assert "onboarding_completed_at" in cols, (
            "tenant.onboarding_completed_at column is missing — required to "
            "replace the !workspace_id proxy in the FE post-auth callback."
        )

    @pytest.mark.asyncio
    async def test_onboarding_completed_at_is_nullable_timestamptz(self, test_engine):
        """
        The column must be nullable (default NULL = onboarding not done)
        and TIMESTAMP WITH TIME ZONE (matches the rest of this schema's
        timestamps — see status_updated_at, created_at, etc.).
        """
        async with test_engine.connect() as conn:
            cols = await conn.run_sync(
                lambda sync_conn: {
                    c["name"]: c
                    for c in sa.inspect(sync_conn).get_columns("tenant")
                }
            )
        col = cols["onboarding_completed_at"]
        assert col["nullable"] is True, (
            "onboarding_completed_at must be NULL until the wizard completes."
        )
        # SQLAlchemy reports the bare type name as 'TIMESTAMP' regardless
        # of timezone awareness; the discriminator is the `timezone`
        # attribute on the type object.
        col_type = col["type"]
        assert isinstance(col_type, sa.TIMESTAMP), (
            f"onboarding_completed_at must be a TIMESTAMP type; got {type(col_type).__name__}"
        )
        assert col_type.timezone is True, (
            f"onboarding_completed_at must be TIMESTAMP WITH TIME ZONE; "
            f"got timezone={col_type.timezone!r}"
        )

    @pytest.mark.asyncio
    async def test_can_round_trip_onboarding_completed_at(self, test_engine):
        """
        Insert a tenant with onboarding_completed_at unset, stamp it via
        UPDATE, read back. Proves the ORM mapping accepts a real datetime
        end-to-end.
        """
        SessionMaker = async_sessionmaker(bind=test_engine, expire_on_commit=False)
        suffix = _unique()
        tenant_id = str(uuid.uuid4())

        try:
            async with SessionMaker() as setup:
                async with setup.begin():
                    setup.add(
                        Tenant(
                            id=tenant_id,
                            name=f"acme-{suffix}",
                            org_external_id=f"acme-{suffix}",
                            status=TenantStatusEnum.ACTIVE,
                            created_at=datetime.now(UTC),
                            updated_at=datetime.now(UTC),
                        )
                    )

            async with SessionMaker() as verify:
                row = await verify.get(Tenant, tenant_id)
                assert row is not None
                assert row.onboarding_completed_at is None, (
                    "New tenants must default to onboarding_completed_at = NULL."
                )

            stamp = datetime.now(UTC)
            async with SessionMaker() as stamp_session:
                async with stamp_session.begin():
                    await stamp_session.execute(
                        sa.update(Tenant)
                        .where(Tenant.id == tenant_id)
                        .values(onboarding_completed_at=stamp)
                    )

            async with SessionMaker() as verify:
                row = await verify.get(Tenant, tenant_id)
                assert row is not None
                assert row.onboarding_completed_at is not None
                # Postgres TIMESTAMPTZ round-trips with timezone preserved.
                assert row.onboarding_completed_at.tzinfo is not None
        finally:
            async with SessionMaker() as cleanup:
                async with cleanup.begin():
                    await cleanup.execute(
                        sa.delete(Tenant).where(Tenant.id == tenant_id)
                    )


class TestWorkspacePillarsColumn:
    """Workspace gains a multi-select enabled_pillars array."""

    @pytest.mark.asyncio
    async def test_workspace_table_has_enabled_pillars_column(self, test_engine):
        """
        Workspace must carry per-workspace pillar selection. Today this
        is conflated into orchestrator_config.router_mode (single enum).
        The wizard wants real multi-select per locked product decision.
        """
        async with test_engine.connect() as conn:
            cols = await conn.run_sync(
                lambda sync_conn: {
                    c["name"]: c
                    for c in sa.inspect(sync_conn).get_columns("workspace")
                }
            )
        assert "enabled_pillars" in cols, (
            "workspace.enabled_pillars column is missing — required to "
            "replace the single-value router_mode with multi-select."
        )

    @pytest.mark.asyncio
    async def test_enabled_pillars_defaults_to_empty_array(self, test_engine):
        """
        A freshly inserted workspace with no pillar selection defaults
        to an empty array (NOT NULL, server_default='{}'). Onboarding
        wizard step 2 sets the real value.
        """
        SessionMaker = async_sessionmaker(bind=test_engine, expire_on_commit=False)
        suffix = _unique()
        tenant_id = str(uuid.uuid4())
        workspace_id = str(uuid.uuid4())

        try:
            async with SessionMaker() as setup:
                async with setup.begin():
                    setup.add(
                        Tenant(
                            id=tenant_id,
                            name=f"acme-{suffix}",
                            org_external_id=f"acme-{suffix}",
                            status=TenantStatusEnum.ACTIVE,
                            created_at=datetime.now(UTC),
                            updated_at=datetime.now(UTC),
                        )
                    )
                    setup.add(
                        Workspace(
                            id=workspace_id,
                            tenant_id=tenant_id,
                            name=f"main-{suffix}",
                            status=WorkspaceStatusEnum.ACTIVE,
                            created_at=datetime.now(UTC),
                            updated_at=datetime.now(UTC),
                        )
                    )

            async with SessionMaker() as verify:
                row = await verify.get(Workspace, workspace_id)
                assert row is not None
                assert row.enabled_pillars == [], (
                    f"enabled_pillars must default to []; got {row.enabled_pillars!r}"
                )
        finally:
            async with SessionMaker() as cleanup:
                async with cleanup.begin():
                    await cleanup.execute(
                        sa.delete(Workspace).where(Workspace.id == workspace_id)
                    )
                    await cleanup.execute(
                        sa.delete(Tenant).where(Tenant.id == tenant_id)
                    )

    @pytest.mark.asyncio
    async def test_can_round_trip_enabled_pillars_with_all_three(self, test_engine):
        """
        Set enabled_pillars to all three pillars, read back, confirm
        the array preserves contents. This is the AUTO-equivalent
        state — what the wizard defaults to.
        """
        from neutrino_database.models.enums import PillarEnum

        SessionMaker = async_sessionmaker(bind=test_engine, expire_on_commit=False)
        suffix = _unique()
        tenant_id = str(uuid.uuid4())
        workspace_id = str(uuid.uuid4())
        all_pillars = [
            PillarEnum.ENTERPRISE_SEARCH,
            PillarEnum.DATA_ANALYTICS,
            PillarEnum.WORKFLOW_EXECUTION,
        ]

        try:
            async with SessionMaker() as setup:
                async with setup.begin():
                    setup.add(
                        Tenant(
                            id=tenant_id,
                            name=f"acme-{suffix}",
                            org_external_id=f"acme-{suffix}",
                            status=TenantStatusEnum.ACTIVE,
                            created_at=datetime.now(UTC),
                            updated_at=datetime.now(UTC),
                        )
                    )
                    setup.add(
                        Workspace(
                            id=workspace_id,
                            tenant_id=tenant_id,
                            name=f"main-{suffix}",
                            status=WorkspaceStatusEnum.ACTIVE,
                            enabled_pillars=all_pillars,
                            created_at=datetime.now(UTC),
                            updated_at=datetime.now(UTC),
                        )
                    )

            async with SessionMaker() as verify:
                row = await verify.get(Workspace, workspace_id)
                assert row is not None
                assert [
                    p.value if hasattr(p, "value") else p
                    for p in row.enabled_pillars
                ] == [p.value for p in all_pillars]
        finally:
            async with SessionMaker() as cleanup:
                async with cleanup.begin():
                    await cleanup.execute(
                        sa.delete(Workspace).where(Workspace.id == workspace_id)
                    )
                    await cleanup.execute(
                        sa.delete(Tenant).where(Tenant.id == tenant_id)
                    )


class TestPillarEnum:
    """The `pillar` enum defines exactly the three product pillars."""

    def test_pillar_enum_has_exactly_three_values(self):
        from neutrino_database.models.enums import PillarEnum

        assert {p.value for p in PillarEnum} == {
            "ENTERPRISE_SEARCH",
            "DATA_ANALYTICS",
            "WORKFLOW_EXECUTION",
        }, (
            "PillarEnum must define exactly the three product pillars; "
            "any addition is a real product decision (not a schema tweak)."
        )

    def test_pillar_enum_values_are_uppercase_per_naming_convention(self):
        from neutrino_database.models.enums import PillarEnum

        # `our-engineering-standards.md` §2: enum values UPPERCASE.
        # ConnectionStatus was the lowercase outlier; we don't add a
        # second one.
        for member in PillarEnum:
            assert member.value == member.value.upper(), (
                f"PillarEnum.{member.name} must be UPPERCASE; got {member.value!r}"
            )
