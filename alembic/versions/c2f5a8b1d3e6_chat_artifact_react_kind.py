"""NC-151 — add the `react` kind to chat_artifact_kind.

Convergence: emit_artifact becomes the SINGLE artifact mechanism, subsuming the
legacy inline ```jsx answer artifact. The `react` kind carries an interactive
React + Tailwind component (compiled in the sandboxed artifact runtime), so the
model no longer needs to inline jsx in its prose.

Forward-only. Removing an enum value in Postgres means recreating the type; with
no rows on this value pre-production, the downgrade is a documented no-op.

Revision ID: c2f5a8b1d3e6
Revises: b8d1c4e6f2a9
Create Date: 2026-07-01
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "c2f5a8b1d3e6"
down_revision: Union[str, Sequence[str], None] = "b8d1c4e6f2a9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # PG 12+ allows ADD VALUE inside a transaction as long as the value isn't
    # used in the same transaction (it isn't here).
    op.execute("ALTER TYPE chat_artifact_kind ADD VALUE IF NOT EXISTS 'react'")


def downgrade() -> None:
    # Postgres can't DROP an enum value; recreating the type just to remove an
    # unused label isn't worth it pre-production. No-op.
    pass
