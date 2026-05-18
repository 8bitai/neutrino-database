"""Harden dashboard_link_token for production-grade share links (DA-P3.4).

DA-P3.1 shipped a v1 ``dashboard_link_token`` table sufficient for "mint
a token and look it up." This migration brings it to the production-grade
share-link shape mature systems converge on (Stripe API keys / GitHub
PATs / Notion link-share):

  * Plaintext ``token`` column is replaced by ``token_hash`` (SHA-256 of
    the URL-safe token, hex-encoded, 64 chars). Plaintext materialises
    exactly once — in the response of the mint endpoint. A DB read can
    confirm a presented token matches a stored row but cannot
    reconstruct it.
  * ``token_short`` carries the first 8 chars of the URL-safe plaintext
    in the clear, set once at mint, for human identification in the
    share dialog ("link · xK4f2nM9"). Same idea as GitHub PAT listings
    showing ``ghp_xxxxXXXX``.
  * ``revoked_by_user_id`` closes the audit-trail gap from v1 — v1
    recorded WHEN a link was revoked but not WHO did it. SOC 2 +
    compliance frame the audit trail as "who did what when"; the
    revoker FK rounds that out.
  * Two cheap CHECK constraints reject incoherent temporal states
    (expires_at <= created_at, revoked_at < created_at) at the DB
    boundary.
  * The plain ``ix_dashboard_link_token_dashboard`` index is replaced
    by a partial index whose WHERE clause exactly matches the
    active-link predicate the Library uses for its Shared-pill JOIN
    (``revoked_at IS NULL AND (expires_at IS NULL OR expires_at >
    now())``). Partial = index doesn't point at revoked / expired rows,
    so it stays small as link history accumulates.

Data-loss safety: no service writes to dashboard_link_token yet (DA-P3.4
is the slice that introduces the mint flow). The migration drops the v1
``token`` column outright with no backfill on the assumption of zero
rows — if any dev DB has stray rows from manual probing, the migration
will fail the NOT NULL on the new ``token_hash``, which is the right
behaviour: surface the inconsistency rather than silently lose the
token. Truncate the table first in that case (no production data
exists).

Revision ID: e8f9a0b1c2d3
Revises: c6d7e8f9a0b1
Create Date: 2026-05-17
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID


revision: str = "e8f9a0b1c2d3"
down_revision: Union[str, Sequence[str], None] = "c6d7e8f9a0b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Drop v1 plaintext token column + its unique index. ---
    # No service mints tokens yet; the table is empty on every
    # environment that's run through DA-P3.1.
    op.drop_index(
        "ux_dashboard_link_token_token", table_name="dashboard_link_token"
    )
    op.drop_column("dashboard_link_token", "token")

    # --- Drop v1 plain dashboard_id index — replaced by partial below. ---
    op.drop_index(
        "ix_dashboard_link_token_dashboard",
        table_name="dashboard_link_token",
    )

    # --- New columns. ---
    # token_hash and token_short are NOT NULL but the table is empty,
    # so no DEFAULT or backfill is needed. Production-grade Alembic
    # patterns add a transient server_default for non-empty tables;
    # we deliberately skip that here to surface any stray rows
    # immediately rather than backfill them with a sentinel.
    op.add_column(
        "dashboard_link_token",
        sa.Column("token_hash", sa.String(64), nullable=False),
    )
    op.add_column(
        "dashboard_link_token",
        sa.Column("token_short", sa.String(12), nullable=False),
    )
    op.add_column(
        "dashboard_link_token",
        sa.Column(
            "revoked_by_user_id",
            UUID(as_uuid=False),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_dashboard_link_token_revoked_by_user_id",
        "dashboard_link_token",
        "user",
        ["revoked_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # --- Temporal CHECK constraints. ---
    op.create_check_constraint(
        "ck_dashboard_link_token_expires_after_created",
        "dashboard_link_token",
        "expires_at IS NULL OR expires_at > created_at",
    )
    op.create_check_constraint(
        "ck_dashboard_link_token_revoked_after_created",
        "dashboard_link_token",
        "revoked_at IS NULL OR revoked_at >= created_at",
    )

    # --- Unique index on the hash. ---
    op.create_index(
        "ux_dashboard_link_token_token_hash",
        "dashboard_link_token",
        ["token_hash"],
        unique=True,
    )

    # --- Active-link partial index. ---
    # Powers the Library's "Shared · N" pill JOIN. Postgres won't
    # accept ``now()`` (STABLE) inside an index predicate so the
    # index filters on ``revoked_at IS NULL`` only — the query layer
    # applies the ``expires_at`` residual at scan time. Standard
    # share-link pattern (Stripe API keys, GitHub PATs).
    op.create_index(
        "ix_dashboard_link_token_active",
        "dashboard_link_token",
        ["dashboard_id"],
        postgresql_where=sa.text("revoked_at IS NULL"),
    )


def downgrade() -> None:
    # Reverse-order teardown. Drop partial + unique indexes, then
    # CHECK constraints, then the new columns + revoker FK, then
    # restore the v1 plaintext token column and its indexes.
    op.drop_index(
        "ix_dashboard_link_token_active", table_name="dashboard_link_token"
    )
    op.drop_index(
        "ux_dashboard_link_token_token_hash",
        table_name="dashboard_link_token",
    )

    op.drop_constraint(
        "ck_dashboard_link_token_revoked_after_created",
        "dashboard_link_token",
        type_="check",
    )
    op.drop_constraint(
        "ck_dashboard_link_token_expires_after_created",
        "dashboard_link_token",
        type_="check",
    )

    op.drop_constraint(
        "fk_dashboard_link_token_revoked_by_user_id",
        "dashboard_link_token",
        type_="foreignkey",
    )
    op.drop_column("dashboard_link_token", "revoked_by_user_id")
    op.drop_column("dashboard_link_token", "token_short")
    op.drop_column("dashboard_link_token", "token_hash")

    # Restore v1 plaintext token column + its indexes.
    op.add_column(
        "dashboard_link_token",
        sa.Column("token", sa.String(128), nullable=False),
    )
    op.create_index(
        "ux_dashboard_link_token_token",
        "dashboard_link_token",
        ["token"],
        unique=True,
    )
    op.create_index(
        "ix_dashboard_link_token_dashboard",
        "dashboard_link_token",
        ["dashboard_id"],
    )
