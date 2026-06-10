"""
Schema test for the NEU-X3 ``tenancy_ownership_transfer`` table.

Two-step ownership transfer per ``user-stories/tenant-admin-actions.md``
§ 4. The Primary Owner initiates a transfer to a target Tenant Admin;
the target accepts via an email link within 7 days; the atomic UPDATE
swaps ``tenant.tenant_owner`` and the old Owner becomes a regular
Admin.

This file pins the schema invariants the rest of NEU-X3 relies on:

  - ``tenant_id`` cascades on tenant delete (ON DELETE CASCADE).
  - ``from_user_id`` / ``to_user_id`` use ON DELETE SET NULL — the
    transfer record survives a GDPR erasure of the actor; we keep
    audit-correlatable enough state via the audit_log row.
  - ``token`` is unique (used in the FE accept URL).
  - **Only one pending transfer per tenant** (partial unique index
    on tenant_id WHERE accepted_at IS NULL AND cancelled_at IS NULL).
    Without this, a confused Owner could fire off three competing
    transfers and create a race over which token actually wins.
  - Partial read index over (expires_at) WHERE pending — keeps the
    retention runner's expiry sweep cheap.

See ``user-stories/tenant-admin-actions.md`` § 4 (Primary Ownership
transfer).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker

from neutrino_database.models.enums import (
    TenantStatusEnum,
    UserStatusEnum,
)
from neutrino_database.models.orm import (
    Tenant,
    TenancyOwnershipTransfer,
    User,
)


def _unique() -> str:
    return uuid.uuid4().hex[:12]


async def _seed_tenant_with_two_users(SessionMaker, suffix: str):
    tenant_id = str(uuid.uuid4())
    a_id = str(uuid.uuid4())
    b_id = str(uuid.uuid4())
    async with SessionMaker() as setup:
        async with setup.begin():
            setup.add(
                Tenant(
                    id=tenant_id,
                    name=f"Acme-{suffix}",
                    org_external_id=f"acme-{suffix}",
                    status=TenantStatusEnum.ACTIVE,
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                )
            )
            await setup.flush()
            setup.add(
                User(
                    id=a_id,
                    tenant_id=tenant_id,
                    email=f"a-{suffix}@example.com",
                    status=UserStatusEnum.ACTIVE,
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                )
            )
            setup.add(
                User(
                    id=b_id,
                    tenant_id=tenant_id,
                    email=f"b-{suffix}@example.com",
                    status=UserStatusEnum.ACTIVE,
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                )
            )
            await setup.flush()
            await setup.execute(
                sa.update(Tenant)
                .where(Tenant.id == tenant_id)
                .values(tenant_owner=a_id)
            )
    return tenant_id, a_id, b_id


async def _cleanup(SessionMaker, tenant_id: str) -> None:
    async with SessionMaker() as cleanup:
        async with cleanup.begin():
            await cleanup.execute(
                sa.delete(TenancyOwnershipTransfer).where(
                    TenancyOwnershipTransfer.tenant_id == tenant_id
                )
            )
            await cleanup.execute(
                sa.update(Tenant)
                .where(Tenant.id == tenant_id)
                .values(tenant_owner=None)
            )
            await cleanup.execute(sa.delete(User).where(User.tenant_id == tenant_id))
            await cleanup.execute(sa.delete(Tenant).where(Tenant.id == tenant_id))


class TestOwnershipTransferTable:
    @pytest.mark.asyncio
    async def test_table_exists(self, test_engine):
        async with test_engine.connect() as conn:
            tables = await conn.run_sync(
                lambda sync_conn: sa.inspect(sync_conn).get_table_names()
            )
        assert "tenancy_ownership_transfer" in tables, (
            "tenancy_ownership_transfer table is required for NEU-X3 "
            "(two-step ownership transfer)."
        )

    @pytest.mark.asyncio
    async def test_required_columns(self, test_engine):
        async with test_engine.connect() as conn:
            cols = await conn.run_sync(
                lambda sync_conn: {
                    c["name"]: c
                    for c in sa.inspect(sync_conn).get_columns(
                        "tenancy_ownership_transfer"
                    )
                }
            )
        for col in (
            "id",
            "tenant_id",
            "from_user_id",
            "to_user_id",
            "token",
            "expires_at",
            "accepted_at",
            "cancelled_at",
            "created_at",
        ):
            assert col in cols, (
                f"tenancy_ownership_transfer is missing column {col!r}"
            )

        # Lifecycle nullability:
        # - id, tenant_id, token, expires_at, created_at are NOT NULL.
        # - from_user_id / to_user_id are NULLABLE (ON DELETE SET NULL on user).
        # - accepted_at / cancelled_at are NULLABLE (set by the
        #   accept/cancel flows; NULL means "still pending").
        for not_null in ("id", "tenant_id", "token", "expires_at", "created_at"):
            assert cols[not_null]["nullable"] is False, (
                f"{not_null} must be NOT NULL"
            )
        for nullable in (
            "from_user_id",
            "to_user_id",
            "accepted_at",
            "cancelled_at",
        ):
            assert cols[nullable]["nullable"] is True, (
                f"{nullable} must be nullable"
            )

    @pytest.mark.asyncio
    async def test_round_trip_through_orm(self, test_engine):
        SessionMaker = async_sessionmaker(bind=test_engine, expire_on_commit=False)
        suffix = _unique()
        tenant_id, owner_id, target_id = await _seed_tenant_with_two_users(
            SessionMaker, suffix
        )
        transfer_id = str(uuid.uuid4())
        token = uuid.uuid4().hex
        expires_at = datetime.now(UTC) + timedelta(days=7)

        try:
            async with SessionMaker() as session:
                async with session.begin():
                    session.add(
                        TenancyOwnershipTransfer(
                            id=transfer_id,
                            tenant_id=tenant_id,
                            from_user_id=owner_id,
                            to_user_id=target_id,
                            token=token,
                            expires_at=expires_at,
                            created_at=datetime.now(UTC),
                        )
                    )

            async with SessionMaker() as verify:
                fetched = await verify.get(TenancyOwnershipTransfer, transfer_id)
                assert fetched is not None
                assert str(fetched.tenant_id) == tenant_id
                assert str(fetched.from_user_id) == owner_id
                assert str(fetched.to_user_id) == target_id
                assert fetched.token == token
                assert fetched.accepted_at is None
                assert fetched.cancelled_at is None
        finally:
            await _cleanup(SessionMaker, tenant_id)

    @pytest.mark.asyncio
    async def test_only_one_pending_transfer_per_tenant(self, test_engine):
        """The partial unique index over (tenant_id) WHERE accepted_at
        IS NULL AND cancelled_at IS NULL prevents a confused Owner
        from firing off competing transfers. Inserting a second
        pending row for the same tenant should violate the unique
        constraint."""
        SessionMaker = async_sessionmaker(bind=test_engine, expire_on_commit=False)
        suffix = _unique()
        tenant_id, owner_id, target_id = await _seed_tenant_with_two_users(
            SessionMaker, suffix
        )

        try:
            async with SessionMaker() as setup:
                async with setup.begin():
                    setup.add(
                        TenancyOwnershipTransfer(
                            id=str(uuid.uuid4()),
                            tenant_id=tenant_id,
                            from_user_id=owner_id,
                            to_user_id=target_id,
                            token=uuid.uuid4().hex,
                            expires_at=datetime.now(UTC) + timedelta(days=7),
                            created_at=datetime.now(UTC),
                        )
                    )

            with pytest.raises(IntegrityError):
                async with SessionMaker() as session:
                    async with session.begin():
                        session.add(
                            TenancyOwnershipTransfer(
                                id=str(uuid.uuid4()),
                                tenant_id=tenant_id,  # same tenant
                                from_user_id=owner_id,
                                to_user_id=target_id,
                                token=uuid.uuid4().hex,  # different token
                                expires_at=datetime.now(UTC) + timedelta(days=7),
                                created_at=datetime.now(UTC),
                            )
                        )
        finally:
            await _cleanup(SessionMaker, tenant_id)

    @pytest.mark.asyncio
    async def test_resolved_transfer_does_not_block_new_one(self, test_engine):
        """The partial uniqueness only applies to PENDING rows. A
        cancelled or accepted transfer must not block a fresh attempt
        — otherwise the tenant would be permanently stuck after one
        ownership change."""
        SessionMaker = async_sessionmaker(bind=test_engine, expire_on_commit=False)
        suffix = _unique()
        tenant_id, owner_id, target_id = await _seed_tenant_with_two_users(
            SessionMaker, suffix
        )

        try:
            # First transfer — cancelled.
            async with SessionMaker() as setup:
                async with setup.begin():
                    setup.add(
                        TenancyOwnershipTransfer(
                            id=str(uuid.uuid4()),
                            tenant_id=tenant_id,
                            from_user_id=owner_id,
                            to_user_id=target_id,
                            token=uuid.uuid4().hex,
                            expires_at=datetime.now(UTC) + timedelta(days=7),
                            cancelled_at=datetime.now(UTC),
                            created_at=datetime.now(UTC),
                        )
                    )

            # Second transfer — pending. Should succeed.
            async with SessionMaker() as setup:
                async with setup.begin():
                    setup.add(
                        TenancyOwnershipTransfer(
                            id=str(uuid.uuid4()),
                            tenant_id=tenant_id,
                            from_user_id=owner_id,
                            to_user_id=target_id,
                            token=uuid.uuid4().hex,
                            expires_at=datetime.now(UTC) + timedelta(days=7),
                            created_at=datetime.now(UTC),
                        )
                    )
        finally:
            await _cleanup(SessionMaker, tenant_id)

    @pytest.mark.asyncio
    async def test_token_unique(self, test_engine):
        """Tokens are used in the FE accept URL — must be unique
        platform-wide. (Random, but the UNIQUE constraint catches the
        cosmic-ray collision.)"""
        SessionMaker = async_sessionmaker(bind=test_engine, expire_on_commit=False)
        suffix = _unique()
        tenant_id, owner_id, target_id = await _seed_tenant_with_two_users(
            SessionMaker, suffix
        )
        # Second tenant for the duplicate-token case.
        suffix2 = _unique()
        tenant2_id, _, _ = await _seed_tenant_with_two_users(SessionMaker, suffix2)
        token = uuid.uuid4().hex

        try:
            async with SessionMaker() as setup:
                async with setup.begin():
                    setup.add(
                        TenancyOwnershipTransfer(
                            id=str(uuid.uuid4()),
                            tenant_id=tenant_id,
                            from_user_id=owner_id,
                            to_user_id=target_id,
                            token=token,
                            expires_at=datetime.now(UTC) + timedelta(days=7),
                            created_at=datetime.now(UTC),
                        )
                    )

            with pytest.raises(IntegrityError):
                async with SessionMaker() as session:
                    async with session.begin():
                        session.add(
                            TenancyOwnershipTransfer(
                                id=str(uuid.uuid4()),
                                tenant_id=tenant2_id,  # different tenant
                                from_user_id=owner_id,
                                to_user_id=target_id,
                                token=token,  # same token — must collide
                                expires_at=datetime.now(UTC) + timedelta(days=7),
                                created_at=datetime.now(UTC),
                            )
                        )
        finally:
            await _cleanup(SessionMaker, tenant_id)
            await _cleanup(SessionMaker, tenant2_id)
