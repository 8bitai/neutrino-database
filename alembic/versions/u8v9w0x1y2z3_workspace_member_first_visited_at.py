"""Add workspace_member.first_visited_at for the cinematic-welcome trigger.

The X-WORKSPACE-MEMBER-UX-1 cinematic plays once per member-per-workspace
on first visit (not first-ever-Neutrino-visit — joining a new workspace
is a meaningful new context). Tracking is per-membership-row rather
than per-user so a member who is removed and re-added to the same
workspace gets a fresh welcome.

Nullable timestamp: NULL means "hasn't visited yet"; non-NULL means
"visited at this time". The FE POSTs to a /membership/first-visit
endpoint after the cinematic dismisses; backend writes
``first_visited_at = now()`` idempotently (no-op if already set).

Revision ID: u8v9w0x1y2z3
Revises: t7u8v9w0x1y2
Create Date: 2026-05-06 11:30:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "u8v9w0x1y2z3"
down_revision: Union[str, Sequence[str], None] = "t7u8v9w0x1y2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "workspace_member",
        sa.Column(
            "first_visited_at",
            sa.TIMESTAMP(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("workspace_member", "first_visited_at")
