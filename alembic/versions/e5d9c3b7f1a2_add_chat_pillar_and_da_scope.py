"""Add chat.pillar + DA data-scope columns (TD-DA-PILLAR-PERSIST).

Persists the pillar a chat was initiated on so it survives reopen /
continue and is authoritative across devices, replacing the browser's
``pillar_for_thread_<id>`` localStorage stopgap. For DA chats we also
persist the data scope (connection + schema) so a reopened DA chat
auto-selects its schema without depending on the global
``selected_schema`` localStorage key.

  * ``chat.pillar`` — nullable ``pillar`` ENUM. Reuses the existing
    ``pillar`` type owned by ``workspace.enabled_pillars`` (created in
    l9m0n1p2q3r4), so ``create_type=False`` — do NOT re-create or drop
    the shared type here. NULL = "no single pillar": Unified chats
    (AUTO, spans all pillars — exempt by design) and legacy rows
    created before this column existed.
  * ``chat.da_connection_name`` / ``chat.da_schema_name`` — nullable
    text, only set when pillar == DATA_ANALYTICS. Mirror the FE
    ``text_to_sql_config``.

No backfill: existing chats stay NULL (treated as Unified/legacy). The
service lazily backfills pillar the first time such a chat is continued
with a specific pillar_mode.

Revision ID: e5d9c3b7f1a2
Revises: d4c8b2a6e0f1
Create Date: 2026-07-02 00:05:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "e5d9c3b7f1a2"
down_revision: Union[str, Sequence[str], None] = "d4c8b2a6e0f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


PILLAR_ENUM_NAME = "pillar"
PILLAR_VALUES = ("ENTERPRISE_SEARCH", "DATA_ANALYTICS", "WORKFLOW_EXECUTION")


def upgrade() -> None:
    op.add_column(
        "chat",
        sa.Column(
            "pillar",
            # Reuse the shared ``pillar`` type — create_type=False so this
            # migration never tries to (re-)create it.
            postgresql.ENUM(
                *PILLAR_VALUES, name=PILLAR_ENUM_NAME, create_type=False
            ),
            nullable=True,
        ),
    )
    op.add_column("chat", sa.Column("da_connection_name", sa.String(), nullable=True))
    op.add_column("chat", sa.Column("da_schema_name", sa.String(), nullable=True))


def downgrade() -> None:
    # Drop only the columns we added — the shared ``pillar`` enum type is
    # owned by workspace.enabled_pillars and must survive.
    op.drop_column("chat", "da_schema_name")
    op.drop_column("chat", "da_connection_name")
    op.drop_column("chat", "pillar")
