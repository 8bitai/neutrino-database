"""Add platform_user — cross-tenant operator accounts (NC-494).

Until now the highest privilege in the system was a per-tenant Primary
Owner, so there was nobody who could create a tenant: the only code path
that ever inserted a `tenant` row was the SSO first-login flow, and that
is gated off by ALLOW_SELF_SERVE_TENANT_SIGNUP. This table gives the
platform an operator identity that exists *outside* every tenant, which
the admin provisioning API authenticates against.

Why a separate table rather than a flag on `user`:

  * `user.tenant_id` is NOT NULL. An operator stored there would have to
    be parked inside some arbitrary tenant, and `ux_user_tenant_email`
    plus every "list the users in this tenant" query would start
    including someone who isn't a member of it.
  * A platform bit on the normal session token would be forwarded to
    downstream services by `mint_internal_token`. Keeping the identity
    on its own table lets the platform token carry a distinct audience
    and no `tenant_id` claim at all, so a downstream service cannot
    mistake it for a tenant principal.

`email` is globally unique here, unlike `user.email` which is unique only
per tenant. That is deliberate: it means the operator login lookup can
never hit the multi-row ambiguity that `LocalAuthService.login` has to
defend against once a second tenant exists.

Revision ID: g1h2i3j4k5l6
Revises: f2a4c6e8b0d2
Create Date: 2026-08-16 10:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "g1h2i3j4k5l6"
down_revision: Union[str, Sequence[str], None] = "f2a4c6e8b0d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    platform_user_status = postgresql.ENUM(
        "ACTIVE",
        "DISABLED",
        name="platform_user_status",
        create_type=False,
    )
    platform_user_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "platform_user",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("email", sa.String(length=320), nullable=False, comment="pii:email"),
        sa.Column("display_name", sa.String(length=255), nullable=True, comment="pii:name"),
        sa.Column(
            "status",
            platform_user_status,
            nullable=False,
            server_default="ACTIVE",
        ),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column(
            "must_change_password",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("password_changed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("last_login_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.UniqueConstraint("email", name="ux_platform_user_email"),
    )

    # Case-insensitive uniqueness among live rows only, so an address can
    # be reused after an operator is soft-deleted. Mirrors
    # ix_user_email_lower_active on the tenant-scoped user table.
    op.create_index(
        "ix_platform_user_email_lower_active",
        "platform_user",
        [sa.text("lower(email)")],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_platform_user_email_lower_active", table_name="platform_user")
    op.drop_table("platform_user")
    postgresql.ENUM(name="platform_user_status").drop(op.get_bind(), checkfirst=True)
