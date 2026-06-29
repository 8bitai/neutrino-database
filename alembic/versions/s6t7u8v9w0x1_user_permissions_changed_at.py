"""Add user.permissions_changed_at for JWT force-renewal (NEU-X8).

Today, when an Owner promotes user B to Tenant Admin, the FGA tuple is
written immediately and the gateway treats B as admin on the next
request — but B's existing JWT still carries `is_tenant_admin: false`.
The FE reads from the JWT (per single-source-of-truth rule) so B's UI
stays stuck on "non-admin" until the JWT enters its renewal window
(~45 min) or B signs out + signs in.

This migration adds a single TIMESTAMPTZ column on the `user` row.
The auth middleware compares the JWT's `iat` against this column on
each request; if `permissions_changed_at` is newer, force-renew the
JWT regardless of the normal renewal-window threshold. Mutation sites
(promote/demote tenant admin, promote/demote workspace admin,
ownership transfer accept) bump this column for affected users in the
same transaction as the audit row.

Same shape as Auth0's `password_changed_at` for revoking refresh
tokens issued before a password change. Cheap (one column read per
request, one column write per authz mutation), no distributed cache,
no push infra.

Nullable so existing rows behave like "no change since issuance" —
back-compat: a user with NULL `permissions_changed_at` never triggers
force-renewal. New mutations always populate it. Index on the column
isn't needed — every middleware lookup is by `user.id` (PK) which is
already indexed; we just project this one extra column.

Revision ID: s6t7u8v9w0x1
Revises: r5s6t7u8v9w0
Create Date: 2026-04-29 22:30:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "s6t7u8v9w0x1"
down_revision: Union[str, Sequence[str], None] = "r5s6t7u8v9w0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "user",
        sa.Column(
            "permissions_changed_at",
            sa.TIMESTAMP(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("user", "permissions_changed_at")
