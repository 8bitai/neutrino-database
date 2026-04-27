"""Add workspace_invitation.personal_message for the inviter's optional note.

Persona A's onboarding wizard (FE) sends an optional personal note
along with the invitation. It's persisted on the invitation row so:

  - The invitation email can include it verbatim.
  - "Resend invitation" reuses the same wording.
  - The invitation list UI can show inviters what they wrote.

DB-permissive (TEXT NULL); the gateway caps length at the API boundary
via Pydantic so we can adjust the cap without a schema change.

Revision ID: m0n1p2q3r4s5
Revises: l9m0n1p2q3r4
Create Date: 2026-04-27 22:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "m0n1p2q3r4s5"
down_revision: Union[str, Sequence[str], None] = "l9m0n1p2q3r4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "workspace_invitation",
        sa.Column("personal_message", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("workspace_invitation", "personal_message")
