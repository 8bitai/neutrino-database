"""Schema test for the password-login Member-bridge (X-MEMBER-BRIDGE-1).

The Member table is the user-identity bridge for OpenFGA Store B (per-file
ACLs). Tuples are keyed by ``Member.id``; a user with no Member row cannot
be granted file access and cannot be returned by ``list_my_docs``.

Before X-MEMBER-BRIDGE-1, ``Member`` rows were only created on SSO login —
``IdpProviderEnum`` had only ``AZURE_AD`` and ``GOOGLE_IDENTITY``. Users who
authenticated via local password (anmol8bit@gmail.com, every invited user
who set their own password) had no addressable identity in Store B, so:

  - ``grant_uploader_access`` on file upload silently failed (member lookup
    returned None).
  - ``list_my_docs`` returned ``[]`` for the chat ES agent.
  - The agent narrated "no documents indexed for this workspace yet" even
    when files were ingested.

The fix adds ``NEUTRINO_LOCAL`` to ``IdpProviderEnum`` and ``LOCAL_LOGIN`` to
``MemberSourceEnum`` so password-authed users get the same kind of Member
row SSO users do — keyed by ``(NEUTRINO_LOCAL, user_id)`` because there is
no external IdP to provide a stable ``provider_user_id``.

This test pins:
  1. The new enum values exist in ``IdpProviderEnum`` and ``MemberSourceEnum``.
  2. A Member row can be persisted with the new provider + source.
  3. Round-trips through the ORM.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker

from neutrino_database.models.enums import (
    IdpProviderEnum,
    MemberSourceEnum,
    TenantStatusEnum,
    UserStatusEnum,
)
from neutrino_database.models.orm import Member, Tenant, User


def _unique() -> str:
    return uuid.uuid4().hex[:12]


class TestIdpProviderEnumLocal:
    def test_neutrino_local_provider_exists(self):
        """NEUTRINO_LOCAL must be a valid IdpProviderEnum value.

        Without this, password-login users have no provider value to write
        into the (provider, provider_user_id) unique constraint on Member.
        """
        assert hasattr(IdpProviderEnum, "NEUTRINO_LOCAL"), (
            "IdpProviderEnum must expose NEUTRINO_LOCAL for the local-auth "
            "Member bridge (X-MEMBER-BRIDGE-1)."
        )
        assert IdpProviderEnum.NEUTRINO_LOCAL.value == "NEUTRINO_LOCAL"

    def test_local_login_source_exists(self):
        """LOCAL_LOGIN must be a valid MemberSourceEnum value.

        Distinguishes Member rows minted from a password login from those
        minted via SSO callback (SSO_LOGIN) or file-permission sync
        (FILE_PERMISSIONS) — useful for ops queries and audit.
        """
        assert hasattr(MemberSourceEnum, "LOCAL_LOGIN"), (
            "MemberSourceEnum must expose LOCAL_LOGIN to tag Member rows "
            "minted by local password auth."
        )
        assert MemberSourceEnum.LOCAL_LOGIN.value == "LOCAL_LOGIN"


class TestMemberLocalProviderPersistence:
    @pytest.mark.asyncio
    async def test_member_with_local_provider_persists(self, test_engine):
        """A Member row with provider=NEUTRINO_LOCAL must round-trip.

        ``provider_user_id`` is set to the user's own UUID — there is no
        external IdP to provide one, so the user's id IS the stable
        identifier within the (NEUTRINO_LOCAL, *) namespace.
        ``provider_org_id`` is set to the tenant id — the Member belongs
        to a tenant in the same way SSO-discovered Members belong to a
        provider_org_id.
        """
        SessionMaker = async_sessionmaker(bind=test_engine, expire_on_commit=False)
        suffix = _unique()
        tenant_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        member_id = str(uuid.uuid4())

        try:
            async with SessionMaker() as setup:
                async with setup.begin():
                    setup.add(
                        Tenant(
                            id=tenant_id,
                            name=f"LocalCo-{suffix}",
                            org_external_id=f"local-{suffix}",
                            status=TenantStatusEnum.ACTIVE,
                            created_at=datetime.now(UTC),
                            updated_at=datetime.now(UTC),
                        )
                    )
            async with SessionMaker() as setup_user:
                async with setup_user.begin():
                    setup_user.add(
                        User(
                            id=user_id,
                            tenant_id=tenant_id,
                            email=f"local-{suffix}@example.com",
                            display_name=f"Local {suffix}",
                            status=UserStatusEnum.ACTIVE,
                            created_at=datetime.now(UTC),
                            updated_at=datetime.now(UTC),
                        )
                    )
            async with SessionMaker() as setup_member:
                async with setup_member.begin():
                    setup_member.add(
                        Member(
                            id=member_id,
                            user_id=user_id,
                            email=f"local-{suffix}@example.com",
                            name=f"Local {suffix}",
                            provider=IdpProviderEnum.NEUTRINO_LOCAL,
                            provider_user_id=user_id,
                            provider_org_id=tenant_id,
                            source=MemberSourceEnum.LOCAL_LOGIN,
                            created_at=datetime.now(UTC),
                            updated_at=datetime.now(UTC),
                        )
                    )

            async with SessionMaker() as verify:
                fetched = await verify.get(Member, member_id)
                assert fetched is not None
                assert fetched.provider == IdpProviderEnum.NEUTRINO_LOCAL
                assert fetched.source == MemberSourceEnum.LOCAL_LOGIN
                assert fetched.provider_user_id == user_id
                assert fetched.provider_org_id == tenant_id
                assert fetched.user_id == user_id
        finally:
            async with SessionMaker() as cleanup:
                async with cleanup.begin():
                    await cleanup.execute(
                        sa.delete(Member).where(Member.id == member_id)
                    )
                    await cleanup.execute(
                        sa.delete(User).where(User.id == user_id)
                    )
                    await cleanup.execute(
                        sa.delete(Tenant).where(Tenant.id == tenant_id)
                    )
