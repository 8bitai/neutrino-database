"""NC-149 — chat_attachment.direction (inbound upload vs outbound export).

The table is reused for agent-generated exports: a user asks the Unified
Chat agent to "generate this as a CSV/Excel/PDF/Word report" and gets a
download button. An export shares the exact ephemeral, conversation-scoped,
TTL'd MinIO-blob lifecycle of an upload, so it lives here rather than in a
parallel table. The only new axis is provenance:

  * ``chat_attachment_direction``  inbound | outbound

``inbound`` = user upload (NC-137); ``outbound`` = agent-generated export
(NC-149). ``kind`` stays meaningful across both — a PDF/Word export is
``document``, a CSV/Excel export is ``tabular`` — so no new kind value.

Column is NOT NULL with a server default of ``'inbound'``, so every existing
row backfills correctly and the untouched upload path needs no code change;
only the export path sets ``'outbound'``.

Revision ID: a7c9e2b4d6f8
Revises: 52e581f60dfa
Create Date: 2026-07-01
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ENUM


revision: str = "a7c9e2b4d6f8"
down_revision: Union[str, Sequence[str], None] = "52e581f60dfa"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Shared enum object: created explicitly, then referenced by add_column with
# create_type=False so the column bind doesn't try to auto-create it again.
direction_enum = ENUM(
    "inbound", "outbound",
    name="chat_attachment_direction",
    create_type=False,
)


def upgrade() -> None:
    direction_enum.create(op.get_bind(), checkfirst=False)
    op.add_column(
        "chat_attachment",
        sa.Column(
            "direction",
            direction_enum,
            nullable=False,
            server_default=sa.text("'inbound'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("chat_attachment", "direction")
    sa.Enum(name="chat_attachment_direction").drop(op.get_bind(), checkfirst=False)
