"""Add tenant.allowed_invitation_domains for Owner-controlled allowlist (NEU-X4).

Decouples tenant identity from email domain. Two related fixes
land in NEU-X4:

  1. ``tenant.name`` semantics shift from "email-domain label"
     ('ibm.com') to free-text "Organization name" ('IBM') set by
     the Owner during onboarding via inline edit on /welcome.
     No schema change for the column itself — only the way callers
     populate it.

  2. ``tenant.allowed_invitation_domains`` (this migration) — a
     TEXT[] allowlist the Owner controls in Settings. Empty
     (default) means "no restriction"; any non-empty value gates
     invitations to those domains.

The previous behavior was a hardcoded check inside
``invite_user_to_workspace``: invitee email domain MUST match the
Owner's email domain. That broke for orgs with legitimate multiple
domains (IBM: ibm.com / ibm.co.in / ibm.co.uk; subsidiaries; M&A
transitions). It also blocked test setups that share an email
domain across multiple test tenants.

Default empty array preserves nothing for existing tenants — the
hardcoded check goes away in the gateway commit and the Owner
opts back into enforcement by adding domains in Settings. This is
deliberately permissive-by-default; mirrors Linear / Notion /
GitHub's behavior. Slack-style strict enforcement is one chip-add
away.

Revision ID: q4r5s6t7u8v9
Revises: p3r4s5t6u7v8
Create Date: 2026-04-29 16:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "q4r5s6t7u8v9"
down_revision: Union[str, Sequence[str], None] = "p3r4s5t6u7v8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add as nullable first, backfill empty arrays for any pre-existing
    # rows, then enforce NOT NULL. The server_default covers future
    # inserts so this is a one-shot backfill.
    op.add_column(
        "tenant",
        sa.Column(
            "allowed_invitation_domains",
            sa.dialects.postgresql.ARRAY(sa.Text()),
            nullable=True,
            server_default=sa.text("'{}'::text[]"),
        ),
    )
    op.execute(
        "UPDATE tenant SET allowed_invitation_domains = '{}'::text[] "
        "WHERE allowed_invitation_domains IS NULL"
    )
    op.alter_column("tenant", "allowed_invitation_domains", nullable=False)


def downgrade() -> None:
    op.drop_column("tenant", "allowed_invitation_domains")
