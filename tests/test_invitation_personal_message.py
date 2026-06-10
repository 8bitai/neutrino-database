"""
Schema test for ``workspace_invitation.personal_message``.

Persona A's onboarding wizard (FE) sends an optional personal note
along with the invitation. The note is persisted on the invitation
row so it can be:

  - included in the invitation email when first sent,
  - re-sent when the inviter clicks "Resend",
  - shown in the invitation list UI for the inviter to verify what
    they wrote.

Per `our-engineering-standards.md` §10 (migration discipline) and
§2 (the schema is permissive — Pydantic at the gateway boundary
caps the length).

Pinned by:
  - column existence + nullability,
  - round-trip with a real value,
  - default-NULL when omitted (most invitations won't carry a note).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
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
    WorkspaceInvitation,
)


def _unique() -> str:
    return uuid.uuid4().hex[:12]


@pytest.mark.asyncio
async def test_workspace_invitation_has_personal_message_column(test_engine):
    """The personal_message column must exist (Text, nullable)."""
    async with test_engine.connect() as conn:
        cols = await conn.run_sync(
            lambda sync_conn: {
                c["name"]: c
                for c in sa.inspect(sync_conn).get_columns("workspace_invitation")
            }
        )
    assert "personal_message" in cols, (
        "workspace_invitation.personal_message column is missing — required "
        "for Persona A's invite flow to carry the inviter's note."
    )
    assert cols["personal_message"]["nullable"] is True, (
        "personal_message must be nullable; most invitations carry no note."
    )


@pytest.mark.asyncio
async def test_invitation_round_trips_personal_message(test_engine):
    """Insert with a message, read back, confirm preserved verbatim."""
    SessionMaker = async_sessionmaker(bind=test_engine, expire_on_commit=False)
    suffix = _unique()
    tenant_id = str(uuid.uuid4())
    inviter_id = str(uuid.uuid4())
    workspace_id = str(uuid.uuid4())
    invitation_id = str(uuid.uuid4())
    note = (
        "Hey Sam — I set up Neutrino for the org. Can you take it from "
        "here? Pick the LLM provider, hook up SharePoint, then poke "
        "around. Ping me if anything looks off."
    )

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
                        id=inviter_id,
                        tenant_id=tenant_id,
                        email=f"founder-{suffix}@example.com",
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
                        name=f"main-{suffix}",
                        status=WorkspaceStatusEnum.ACTIVE,
                        created_at=datetime.now(UTC),
                        updated_at=datetime.now(UTC),
                    )
                )
                setup.add(
                    WorkspaceInvitation(
                        id=invitation_id,
                        workspace_id=workspace_id,
                        inviter=inviter_id,
                        email=f"sam-{suffix}@example.com",
                        is_workspace_admin=True,
                        personal_message=note,
                        expires_at=datetime.now(UTC) + timedelta(days=7),
                        created_at=datetime.now(UTC),
                    )
                )

        async with SessionMaker() as verify:
            row = await verify.get(WorkspaceInvitation, invitation_id)
            assert row is not None
            assert row.personal_message == note
    finally:
        async with SessionMaker() as cleanup:
            async with cleanup.begin():
                await cleanup.execute(
                    sa.delete(WorkspaceInvitation).where(
                        WorkspaceInvitation.id == invitation_id
                    )
                )
                await cleanup.execute(
                    sa.delete(Workspace).where(Workspace.id == workspace_id)
                )
                await cleanup.execute(sa.delete(User).where(User.id == inviter_id))
                await cleanup.execute(
                    sa.delete(Tenant).where(Tenant.id == tenant_id)
                )


@pytest.mark.asyncio
async def test_invitation_personal_message_defaults_to_none(test_engine):
    """Omitting personal_message must result in NULL — no sentinel default."""
    SessionMaker = async_sessionmaker(bind=test_engine, expire_on_commit=False)
    suffix = _unique()
    tenant_id = str(uuid.uuid4())
    inviter_id = str(uuid.uuid4())
    workspace_id = str(uuid.uuid4())
    invitation_id = str(uuid.uuid4())

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
                        id=inviter_id,
                        tenant_id=tenant_id,
                        email=f"founder-{suffix}@example.com",
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
                        name=f"main-{suffix}",
                        status=WorkspaceStatusEnum.ACTIVE,
                        created_at=datetime.now(UTC),
                        updated_at=datetime.now(UTC),
                    )
                )
                setup.add(
                    WorkspaceInvitation(
                        id=invitation_id,
                        workspace_id=workspace_id,
                        inviter=inviter_id,
                        email=f"sam-{suffix}@example.com",
                        is_workspace_admin=False,
                        # personal_message intentionally omitted.
                        expires_at=datetime.now(UTC) + timedelta(days=7),
                        created_at=datetime.now(UTC),
                    )
                )

        async with SessionMaker() as verify:
            row = await verify.get(WorkspaceInvitation, invitation_id)
            assert row is not None
            assert row.personal_message is None, (
                "Omitted personal_message must round-trip to NULL — absence "
                "is the meaningful signal that no note was provided."
            )
    finally:
        async with SessionMaker() as cleanup:
            async with cleanup.begin():
                await cleanup.execute(
                    sa.delete(WorkspaceInvitation).where(
                        WorkspaceInvitation.id == invitation_id
                    )
                )
                await cleanup.execute(
                    sa.delete(Workspace).where(Workspace.id == workspace_id)
                )
                await cleanup.execute(sa.delete(User).where(User.id == inviter_id))
                await cleanup.execute(
                    sa.delete(Tenant).where(Tenant.id == tenant_id)
                )
