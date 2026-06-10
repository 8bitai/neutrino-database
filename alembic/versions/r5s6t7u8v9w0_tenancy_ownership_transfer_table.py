"""Add tenancy_ownership_transfer table for two-step ownership transfer (NEU-X3).

Per ``user-stories/tenant-admin-actions.md`` § 4: the Primary Owner
initiates a transfer to a target Tenant Admin; the target accepts
via an email link within 7 days; the atomic UPDATE swaps
``tenant.tenant_owner``. The retention runner (NEU-1805 phase 5c)
sweeps expired pending rows nightly via ``OwnershipTransferExpiryPolicy``.

Schema invariants captured:

  - tenant_id CASCADEs on tenant delete (a tenant being torn down
    obviously can't have a pending ownership transfer dangling).

  - from_user_id / to_user_id use ON DELETE SET NULL — the transfer
    record survives a GDPR Art. 17 erasure of the actor; the
    audit_log row captures the actor identity at time-of-action,
    which is what auditors care about. Cancelling a transfer when
    the initiator is gone is fine — only the new Owner can cancel
    it anyway, but we document this edge case in the gateway
    cancel_transfer service.

  - token UNIQUE — the FE accept URL carries only the token; it
    must identify the transfer globally without needing tenant_id.

  - **Partial unique index** on (tenant_id) WHERE
    accepted_at IS NULL AND cancelled_at IS NULL — only one PENDING
    transfer per tenant. Without this, a confused Owner could fire
    off competing transfers and we'd race over which token wins.
    The expiry runner cancels stale rows, after which a fresh
    transfer can be initiated.

  - Partial read index on (expires_at) WHERE pending — cheap
    sweep predicate for the retention runner.

Revision ID: r5s6t7u8v9w0
Revises: q4r5s6t7u8v9
Create Date: 2026-04-29 17:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "r5s6t7u8v9w0"
down_revision: Union[str, Sequence[str], None] = "q4r5s6t7u8v9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tenancy_ownership_transfer",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "tenant_id",
            sa.dialects.postgresql.UUID(as_uuid=False),
            sa.ForeignKey("tenant.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "from_user_id",
            sa.dialects.postgresql.UUID(as_uuid=False),
            sa.ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "to_user_id",
            sa.dialects.postgresql.UUID(as_uuid=False),
            sa.ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("token", sa.Text(), nullable=False, unique=True),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ux_ownership_transfer_pending_per_tenant",
        "tenancy_ownership_transfer",
        ["tenant_id"],
        unique=True,
        postgresql_where=sa.text("accepted_at IS NULL AND cancelled_at IS NULL"),
    )
    op.create_index(
        "ix_ownership_transfer_token",
        "tenancy_ownership_transfer",
        ["token"],
    )
    op.create_index(
        "ix_ownership_transfer_pending_expires",
        "tenancy_ownership_transfer",
        ["expires_at"],
        postgresql_where=sa.text("accepted_at IS NULL AND cancelled_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ownership_transfer_pending_expires",
        table_name="tenancy_ownership_transfer",
    )
    op.drop_index(
        "ix_ownership_transfer_token",
        table_name="tenancy_ownership_transfer",
    )
    op.drop_index(
        "ux_ownership_transfer_pending_per_tenant",
        table_name="tenancy_ownership_transfer",
    )
    op.drop_table("tenancy_ownership_transfer")
