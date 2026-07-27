"""VAPT D-1 / D-2 — add hash-at-rest token columns (ADDITIVE, backward-compatible).

Two capability tokens are stored in plaintext today:

  * ``tenancy_ownership_transfer.token`` (D-1) — a live tenant-takeover URL if the
    DB is dumped.
  * ``workflow_trigger.token``          (D-2) — a bearer token that can fire any
    workflow via ``POST /triggers/{token}``.

Both mirror the *unhardened* v1 of DA's dashboard_link_token. The hardened
pattern (already used by ``share_link`` and ``dashboard_link_token``) stores
``SHA-256(plaintext)`` in ``token_hash`` (+ a non-secret ``token_short``) and
resolves by hash, so the DB never holds the secret.

This migration is **purely additive**: it adds nullable ``token_hash`` /
``token_short`` columns and a partial-unique index on ``token_hash`` to each
table, and LEAVES the existing plaintext ``token`` column intact. That is a
hard requirement — this is a SHARED library and consumer services
(gateway / workflow) still write and read the plaintext ``token`` column, so
dropping it here would break them.

Rollout (cross-repo follow-up, NOT done here):
  1. (this migration) columns exist, nullable — no behaviour change.
  2. Consumers start populating ``token_hash = sha256(plaintext)`` +
     ``token_short = plaintext[:N]`` on mint, and resolve by hashing the
     presented token instead of reading plaintext.
  3. Backfill ``token_hash`` for existing rows.
  4. Once every consumer resolves by hash, a LATER migration makes ``token_hash``
     NOT NULL and drops the plaintext ``token`` column.

Partial-unique index (``WHERE token_hash IS NOT NULL``) so pre-rollout rows that
carry NULL coexist while populated hashes stay globally unique.

Revision ID: f2b4d6a8c1e3
Revises: e5d9c3b7f1a2
Create Date: 2026-07-24
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "f2b4d6a8c1e3"
down_revision: Union[str, Sequence[str], None] = "e5d9c3b7f1a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # D-1 — tenancy_ownership_transfer
    op.add_column(
        "tenancy_ownership_transfer",
        sa.Column("token_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "tenancy_ownership_transfer",
        sa.Column("token_short", sa.String(length=12), nullable=True),
    )
    op.create_index(
        "ix_ownership_transfer_token_hash",
        "tenancy_ownership_transfer",
        ["token_hash"],
        unique=True,
        postgresql_where=sa.text("token_hash IS NOT NULL"),
    )

    # D-2 — workflow_trigger
    op.add_column(
        "workflow_trigger",
        sa.Column("token_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "workflow_trigger",
        sa.Column("token_short", sa.String(length=12), nullable=True),
    )
    op.create_index(
        "uq_workflow_trigger_token_hash",
        "workflow_trigger",
        ["token_hash"],
        unique=True,
        postgresql_where=sa.text("token_hash IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_workflow_trigger_token_hash", table_name="workflow_trigger")
    op.drop_column("workflow_trigger", "token_short")
    op.drop_column("workflow_trigger", "token_hash")

    op.drop_index(
        "ix_ownership_transfer_token_hash", table_name="tenancy_ownership_transfer"
    )
    op.drop_column("tenancy_ownership_transfer", "token_short")
    op.drop_column("tenancy_ownership_transfer", "token_hash")
