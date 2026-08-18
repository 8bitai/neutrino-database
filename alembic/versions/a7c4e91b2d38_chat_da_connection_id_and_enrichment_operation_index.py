"""Pin a DA chat to a connection by ID, and index enrichment runs by operation.

NC-474. Two additive changes, both driven by the same root cause: a workspace
can legitimately have SEVERAL Postgres connectors, and code that identified
things by name (or ignored a discriminator entirely) breaks once it does.

  * ``chat.da_connection_id`` — the DA chat's pinned connection as a real FK.
    The scope was carried only as ``da_connection_name``, a display string with
    NO uniqueness constraint (``integration.display_name`` is free-form). The
    resolver looked it up with ``scalar_one_or_none()``, so two connectors
    sharing a name raised MultipleResultsFound — a hard 500 on every turn of
    that chat. ``da_connection_name`` is KEPT: it is what the UI renders, it
    backfills legacy chats, and dropping it would break rows we cannot resolve.
    ``ondelete='SET NULL'`` so deleting a connection doesn't cascade away chat
    history; the chat then falls back to name resolution and, failing that,
    tells the user the source is gone.

  * ``ix_da_enrichment_run_connection_operation_status`` — the active-run
    lookup now filters on ``operation`` as well (profiling and description
    generation are independent actions and must be found independently). The
    existing (connection_id, status) index no longer covers that predicate.
    Added alongside rather than replacing it: the two-column index still serves
    the reconciler's operation-blind "is anything active here?" sweep.

No backfill. Existing DA chats keep resolving by name, which is correct for the
single-connector workspaces they were created in.

Revision ID: a7c4e91b2d38
Revises: f8a1c3d5e7b9
Create Date: 2026-08-13 22:10:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "a7c4e91b2d38"
down_revision: Union[str, Sequence[str], None] = "f8a1c3d5e7b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "chat",
        sa.Column("da_connection_id", postgresql.UUID(as_uuid=False), nullable=True),
    )
    op.create_foreign_key(
        "fk_chat_da_connection_id_integration",
        "chat",
        "integration",
        ["da_connection_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_da_enrichment_run_connection_operation_status",
        "da_enrichment_run",
        ["connection_id", "operation", "status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_da_enrichment_run_connection_operation_status",
        table_name="da_enrichment_run",
    )
    op.drop_constraint(
        "fk_chat_da_connection_id_integration", "chat", type_="foreignkey"
    )
    op.drop_column("chat", "da_connection_id")
