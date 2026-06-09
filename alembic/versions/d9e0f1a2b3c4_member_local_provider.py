"""Add NEUTRINO_LOCAL provider + LOCAL_LOGIN source for the Member bridge
(X-MEMBER-BRIDGE-1).

Before this migration, ``IdpProviderEnum`` had only ``AZURE_AD`` and
``GOOGLE_IDENTITY``, so a password-authed user (one who never went through
SSO) could not have a Member row — there was no provider value to satisfy
the ``(provider, provider_user_id)`` unique constraint on ``member``.

Member rows are the user-identity bridge for OpenFGA Store B (per-file
ACLs); tuples are keyed by ``Member.id``. Without a Member row, the
uploader auto-grant (``grant_uploader_access`` from
``ES-Ingestion-Service``) silently no-ops and ``list_my_docs`` returns ``[]``
for the chat ES agent — i.e. the agent narrates "no documents indexed" even
when files are ingested.

This migration adds two enum values:

  * ``idp_provider`` → ``NEUTRINO_LOCAL`` — the synthetic provider for
    password-login users. The user's own ``user.id`` doubles as
    ``provider_user_id`` within this namespace.
  * ``member_source`` → ``LOCAL_LOGIN`` — tags Member rows minted by local
    password auth (distinguishable from SSO_LOGIN and FILE_PERMISSIONS for
    audit and ops queries).

Note: PostgreSQL does not support removing enum values; downgrade is a
no-op. Mirrors the ``c4abbcc55cb8_add_google_idp_provider`` pattern.

Revision ID: d9e0f1a2b3c4
Revises: c8d9e0f1a2b3
Create Date: 2026-05-31
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "d9e0f1a2b3c4"
down_revision: Union[str, Sequence[str], None] = "c8d9e0f1a2b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TYPE idp_provider ADD VALUE IF NOT EXISTS 'NEUTRINO_LOCAL'"
    )
    op.execute(
        "ALTER TYPE member_source ADD VALUE IF NOT EXISTS 'LOCAL_LOGIN'"
    )


def downgrade() -> None:
    # PostgreSQL does not support removing enum values directly.
    # Properly downgrading would require recreating the type without the
    # value and re-pointing every column using it — complex and risky.
    # Left as a no-op; if a downgrade is ever required, confirm no rows
    # use NEUTRINO_LOCAL / LOCAL_LOGIN first.
    pass
