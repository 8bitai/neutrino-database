"""Flip workspace_curation_da_column.allow_sample_values default to true (DA-P1l).

Tier-of-trust decision: tenant compliance gate (PII / Restricted) is the
authoritative line that blocks all profile + sample-value exposure.
Once tenant has cleared a column, the workspace admin gets full
visibility by default — they opted into the curation in the first
place. Workspace admin can opt OUT per column from the detail page
if a specific column should stay aggregate-only inside their
workspace.

Migration:

  * Flip server_default to true so future rows default ON.
  * Backfill every existing row to true. Safe — no UI ever exposed
    the toggle, so every row's current value is the historical
    default (false) rather than a deliberate workspace choice.

Revision ID: a4b5c6d7e8f9
Revises: z3a4b5c6d7e8
Create Date: 2026-05-12
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "a4b5c6d7e8f9"
down_revision: Union[str, Sequence[str], None] = "z3a4b5c6d7e8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "workspace_curation_da_column",
        "allow_sample_values",
        server_default=sa.text("true"),
    )
    op.execute(
        "UPDATE workspace_curation_da_column "
        "SET allow_sample_values = true "
        "WHERE allow_sample_values = false"
    )


def downgrade() -> None:
    op.alter_column(
        "workspace_curation_da_column",
        "allow_sample_values",
        server_default=sa.text("false"),
    )
    # Intentionally NOT reverting backfilled rows — that would clobber
    # any deliberate workspace choice to leave the toggle on after the
    # default flipped. Going back to opt-in semantics is forward-only;
    # the operator can audit + flip individual rows if needed.
