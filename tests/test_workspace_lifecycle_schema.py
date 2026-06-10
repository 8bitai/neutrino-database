"""
Schema tests for the NEU-1805 workspace lifecycle columns.

Phase 5 of the tenant-lifecycle epic gives Tenant Owners production-grade
soft-delete-with-grace for workspaces. The shape is:

  ACTIVE  ──(soft-delete)──▶  PENDING_DELETION  ──(grace expires)──▶  HARD_DELETED
     ▲                                │
     └────────(restore by owner)──────┘

That's encoded by three new columns:

  - ``workspace.deletion_scheduled_for``  — when the retention runner
    will physically remove the row. Stored explicitly (not derived from
    ``deleted_at + 30 days``) so a future change to the grace-period
    constant doesn't silently shift existing pending deletions.
  - ``workspace.deletion_initiated_by``   — audit-correlatable; FK to
    user with ``ON DELETE SET NULL`` so the user row can later be
    anonymized without violating integrity.
  - ``tenant.max_workspaces``             — per-tenant cap (default 50).
    Soft-deleted workspaces don't count toward the cap; the runner
    cleans them up at 30 days.

This file also pins the **partial unique index** on
``(workspace.tenant_id, workspace.name) WHERE deleted_at IS NULL``
that replaces the previous full uniqueness constraint. Without the
partial index, soft-deleted workspaces would block a new workspace
with the same name during the grace period — which would be a real
UX bug because the deletion may yet be reversed.

See ``user-stories/tenant-admin-actions.md`` § 1c (soft-delete with
grace) and § 1d (per-tenant cap) for the product-level spec.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker

from neutrino_database.models.enums import (
    TenantStatusEnum,
    UserStatusEnum,
    WorkspaceStatusEnum,
)
from neutrino_database.models.orm import (
    Tenant,
    User,
    Workspace,
)


def _unique() -> str:
    return uuid.uuid4().hex[:12]


# ---------------------------------------------------------------------------
# workspace.deletion_scheduled_for + deletion_initiated_by columns
# ---------------------------------------------------------------------------


class TestWorkspaceDeletionColumns:
    @pytest.mark.asyncio
    async def test_deletion_scheduled_for_column_exists(self, test_engine):
        """The column must exist, be TIMESTAMPTZ, and be nullable —
        NULL means ACTIVE; non-NULL means PENDING_DELETION."""
        async with test_engine.connect() as conn:
            cols = await conn.run_sync(
                lambda sync_conn: {
                    c["name"]: c
                    for c in sa.inspect(sync_conn).get_columns("workspace")
                }
            )
        assert "deletion_scheduled_for" in cols, (
            "workspace.deletion_scheduled_for is required for the "
            "soft-delete-with-grace flow (NEU-1805 phase 5)."
        )
        assert cols["deletion_scheduled_for"]["nullable"] is True
        col_type = cols["deletion_scheduled_for"]["type"]
        assert isinstance(col_type, sa.TIMESTAMP)
        assert col_type.timezone is True, (
            "deletion_scheduled_for must be TIMESTAMP WITH TIME ZONE — "
            "the retention runner compares it against now()."
        )

    @pytest.mark.asyncio
    async def test_deletion_initiated_by_column_exists(self, test_engine):
        """The column must exist, be UUID, nullable, and FK to user(id)."""
        async with test_engine.connect() as conn:
            cols = await conn.run_sync(
                lambda sync_conn: {
                    c["name"]: c
                    for c in sa.inspect(sync_conn).get_columns("workspace")
                }
            )
            fks = await conn.run_sync(
                lambda sync_conn: sa.inspect(sync_conn).get_foreign_keys("workspace")
            )
        assert "deletion_initiated_by" in cols, (
            "workspace.deletion_initiated_by is required so audit logs "
            "can correlate deletion with the actor."
        )
        assert cols["deletion_initiated_by"]["nullable"] is True

        matching_fks = [
            fk for fk in fks
            if "deletion_initiated_by" in fk["constrained_columns"]
        ]
        assert len(matching_fks) == 1, (
            f"Expected exactly one FK on deletion_initiated_by; got {matching_fks!r}"
        )
        fk = matching_fks[0]
        assert fk["referred_table"] == "user"
        assert fk["referred_columns"] == ["id"]
        # Must be ON DELETE SET NULL so a user can be anonymized
        # (per GDPR Art. 17) without breaking workspace audit history.
        opts = fk.get("options") or {}
        assert opts.get("ondelete") == "SET NULL", (
            f"deletion_initiated_by FK must be ON DELETE SET NULL "
            f"(GDPR-compliant anonymization); got {opts!r}"
        )

    @pytest.mark.asyncio
    async def test_deletion_columns_round_trip(self, test_engine):
        """A workspace can be marked for pending deletion and the
        timestamps + FK round-trip through the ORM cleanly."""
        SessionMaker = async_sessionmaker(bind=test_engine, expire_on_commit=False)
        suffix = _unique()
        tenant_id = str(uuid.uuid4())
        owner_id = str(uuid.uuid4())
        workspace_id = str(uuid.uuid4())
        scheduled_for = datetime(2027, 1, 1, tzinfo=UTC)

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
                    await setup.flush()
                    setup.add(
                        User(
                            id=owner_id,
                            tenant_id=tenant_id,
                            email=f"owner-{suffix}@example.com",
                            status=UserStatusEnum.ACTIVE,
                            created_at=datetime.now(UTC),
                            updated_at=datetime.now(UTC),
                        )
                    )
                    await setup.flush()
                    setup.add(
                        Workspace(
                            id=workspace_id,
                            tenant_id=tenant_id,
                            name="Engineering",
                            status=WorkspaceStatusEnum.ACTIVE,
                            created_by=owner_id,
                            deleted_at=datetime.now(UTC),
                            deletion_scheduled_for=scheduled_for,
                            deletion_initiated_by=owner_id,
                            created_at=datetime.now(UTC),
                            updated_at=datetime.now(UTC),
                        )
                    )

            async with SessionMaker() as verify:
                fetched = await verify.get(Workspace, workspace_id)
                assert fetched is not None
                assert fetched.deleted_at is not None
                assert fetched.deletion_scheduled_for == scheduled_for
                assert str(fetched.deletion_initiated_by) == owner_id
        finally:
            async with SessionMaker() as cleanup:
                async with cleanup.begin():
                    await cleanup.execute(
                        sa.delete(Workspace).where(Workspace.id == workspace_id)
                    )
                    await cleanup.execute(sa.delete(User).where(User.id == owner_id))
                    await cleanup.execute(sa.delete(Tenant).where(Tenant.id == tenant_id))


# ---------------------------------------------------------------------------
# tenant.max_workspaces column
# ---------------------------------------------------------------------------


class TestTenantMaxWorkspaces:
    @pytest.mark.asyncio
    async def test_max_workspaces_column_exists_with_default_50(self, test_engine):
        """The column must exist, be NOT NULL, INTEGER, default 50."""
        async with test_engine.connect() as conn:
            cols = await conn.run_sync(
                lambda sync_conn: {
                    c["name"]: c
                    for c in sa.inspect(sync_conn).get_columns("tenant")
                }
            )
        assert "max_workspaces" in cols, (
            "tenant.max_workspaces is required to cap active workspaces "
            "per tenant (NEU-1805 § 1d)."
        )
        col = cols["max_workspaces"]
        assert col["nullable"] is False, (
            "max_workspaces must be NOT NULL — every tenant has a cap."
        )
        # Default is provided server-side via DEFAULT clause; Postgres
        # reports it as a string '50'.
        default = col.get("default")
        assert default is not None, "max_workspaces must have a server default"
        assert "50" in str(default), (
            f"max_workspaces default should be 50; got {default!r}"
        )

    @pytest.mark.asyncio
    async def test_new_tenant_inherits_default_cap(self, test_engine):
        """Inserting a tenant without specifying max_workspaces should
        land 50 from the server default."""
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
                fetched = await verify.get(Tenant, tenant_id)
                assert fetched is not None
                assert fetched.max_workspaces == 50
        finally:
            async with SessionMaker() as cleanup:
                async with cleanup.begin():
                    await cleanup.execute(sa.delete(Tenant).where(Tenant.id == tenant_id))


# ---------------------------------------------------------------------------
# Partial unique index — name uniqueness only against ACTIVE workspaces
# ---------------------------------------------------------------------------


class TestWorkspaceNameUniquenessIsPartial:
    @pytest.mark.asyncio
    async def test_two_active_workspaces_with_same_name_in_tenant_blocked(
        self, test_engine
    ):
        """Active+active duplicate names are still blocked — that's
        the user-facing uniqueness invariant (no two workspaces named
        'Engineering' in the same tenant at the same time)."""
        SessionMaker = async_sessionmaker(bind=test_engine, expire_on_commit=False)
        suffix = _unique()
        tenant_id = str(uuid.uuid4())
        ws1 = str(uuid.uuid4())
        ws2 = str(uuid.uuid4())

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
                    await setup.flush()
                    setup.add(
                        Workspace(
                            id=ws1,
                            tenant_id=tenant_id,
                            name="Engineering",
                            status=WorkspaceStatusEnum.ACTIVE,
                            created_at=datetime.now(UTC),
                            updated_at=datetime.now(UTC),
                        )
                    )

            with pytest.raises(IntegrityError):
                async with SessionMaker() as session:
                    async with session.begin():
                        session.add(
                            Workspace(
                                id=ws2,
                                tenant_id=tenant_id,
                                name="Engineering",  # duplicate of active row
                                status=WorkspaceStatusEnum.ACTIVE,
                                created_at=datetime.now(UTC),
                                updated_at=datetime.now(UTC),
                            )
                        )
        finally:
            async with SessionMaker() as cleanup:
                async with cleanup.begin():
                    await cleanup.execute(
                        sa.delete(Workspace).where(Workspace.tenant_id == tenant_id)
                    )
                    await cleanup.execute(sa.delete(Tenant).where(Tenant.id == tenant_id))

    @pytest.mark.asyncio
    async def test_soft_deleted_workspace_does_not_block_new_active_with_same_name(
        self, test_engine
    ):
        """The whole point of the partial unique index: a soft-deleted
        workspace must NOT block a new workspace with the same name
        during the 30-day grace period. Without this, deleting
        'Engineering' would make the name unavailable for 30 days
        even though the deletion may yet be reversed.
        """
        SessionMaker = async_sessionmaker(bind=test_engine, expire_on_commit=False)
        suffix = _unique()
        tenant_id = str(uuid.uuid4())
        deleted_ws = str(uuid.uuid4())
        new_ws = str(uuid.uuid4())

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
                    await setup.flush()
                    # Existing soft-deleted workspace named "Engineering".
                    setup.add(
                        Workspace(
                            id=deleted_ws,
                            tenant_id=tenant_id,
                            name="Engineering",
                            status=WorkspaceStatusEnum.ACTIVE,
                            deleted_at=datetime.now(UTC),
                            deletion_scheduled_for=datetime(2027, 1, 1, tzinfo=UTC),
                            created_at=datetime.now(UTC),
                            updated_at=datetime.now(UTC),
                        )
                    )

            # New active workspace with the same name should succeed.
            async with SessionMaker() as session:
                async with session.begin():
                    session.add(
                        Workspace(
                            id=new_ws,
                            tenant_id=tenant_id,
                            name="Engineering",
                            status=WorkspaceStatusEnum.ACTIVE,
                            created_at=datetime.now(UTC),
                            updated_at=datetime.now(UTC),
                        )
                    )

            async with SessionMaker() as verify:
                fetched = await verify.get(Workspace, new_ws)
                assert fetched is not None
                assert fetched.deleted_at is None, (
                    "New workspace must be active (deleted_at is NULL)."
                )
        finally:
            async with SessionMaker() as cleanup:
                async with cleanup.begin():
                    await cleanup.execute(
                        sa.delete(Workspace).where(Workspace.tenant_id == tenant_id)
                    )
                    await cleanup.execute(sa.delete(Tenant).where(Tenant.id == tenant_id))

    @pytest.mark.asyncio
    async def test_active_workspace_unique_index_exists(self, test_engine):
        """The partial unique index should be reported by the inspector
        with the expected `WHERE deleted_at IS NULL` predicate."""
        async with test_engine.connect() as conn:
            indexes = await conn.run_sync(
                lambda sync_conn: sa.inspect(sync_conn).get_indexes("workspace")
            )
        # We only assert the partial-unique invariant: there exists a
        # unique index over (tenant_id, name) with a NULL-on-deleted_at
        # predicate. Index name is implementation detail.
        partial_unique = [
            idx for idx in indexes
            if idx.get("unique")
            and set(idx.get("column_names", [])) == {"tenant_id", "name"}
        ]
        assert partial_unique, (
            "Expected a unique index over (tenant_id, name) on workspace; "
            f"got indexes={indexes!r}."
        )
        # At least one must have a partial predicate. Some Postgres
        # versions surface this on `dialect_options`/`include`
        # variations — check the most-portable place first.
        partial = [
            idx for idx in partial_unique
            if (idx.get("dialect_options") or {})
                .get("postgresql_where") is not None
            or "deleted_at" in str(idx)
        ]
        assert partial, (
            "Expected the (tenant_id, name) unique index to be "
            "partial (WHERE deleted_at IS NULL) so soft-deleted "
            "workspaces don't block new ones with the same name "
            f"during the 30-day grace period. Got {partial_unique!r}."
        )
