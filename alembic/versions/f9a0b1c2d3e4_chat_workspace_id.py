"""Add workspace_id to chat — scope chat threads to a workspace (X-CHAT-WS-1).

The ``chat`` primitive (used by ES + DA ad-hoc Q&A, and by DA
dashboard-build threads) was originally tenant-scoped: rows keyed on
``(tenant_id, created_by, kind, dashboard_id, ...)`` with no
workspace dimension. That model breaks the multi-workspace SaaS UX
— a user who belongs to two workspaces sees the same chat list in
both. Mature systems (Linear, Notion, Slack channels, ChatGPT Teams)
all scope chat threads to a workspace / channel.

Beyond UX, the absence of ``chat.workspace_id`` is a SOC2 / GDPR
isolation gap: the gateway's chat list proxy at
``neutrino-gateway/app/chats/router.py:71`` validated only
tenant-membership, while ``send_message`` at the same file's line
125 already required workspace membership. Without a workspace
column on the row, the list endpoint has nothing to ground
per-workspace authz on, so a Tenant Admin sweep that removes a user
from workspace A leaves their old workspace-A threads visible
inside workspace B.

This migration brings ``chat`` to the workspace-scoped shape:

  * Add ``chat.workspace_id`` UUID NOT NULL with FK CASCADE to
    ``workspace(id)``. Mirrors ``dashboard.workspace_id`` which is
    also CASCADE — deleting a workspace removes its conversational
    history along with its dashboards.
  * Replace ``ix_chat_created_by`` (``tenant_id, created_by``) with
    a partial index ``ix_chat_workspace_created_by_updated_at``
    keyed on ``(workspace_id, created_by, updated_at DESC)`` and
    filtered on ``deleted_at IS NULL``. Matches exactly the FE's
    listChats() predicate; the partial filter keeps the index small
    as soft-deleted history accumulates.

Data-loss safety
----------------
The original workspace context of any existing ``chat`` row is not
recoverable — at creation time the agent-platform service dropped
the workspace_id parameter before INSERT (NEU-1810 lift bug). Best-
effort attribution via ``user.default_workspace_id`` at backfill
time would be visibly wrong (the user's default today is not
necessarily the workspace they were in when chatting).

We deliberately TRUNCATE ``chat`` + ``message`` as part of this
upgrade. The platform is pre-launch dev data only; truncate is
strictly better than nullable-with-legacy-bucket (which would fork
every query path forever). Same call we made for the DA catalog
refactor (DA-P1g).

``runs.session_id`` FK to chat is RESTRICT-ish (no cascade);
TRUNCATE ... CASCADE follows the chat → message → runs chain.
``dashboard.build_chat_id`` is SET NULL on chat delete, so any
dashboard whose build chat is purged survives with NULL build chat
(intentional reciprocal pattern from DA-P3.1).

Revision ID: f9a0b1c2d3e4
Revises: e8f9a0b1c2d3
Create Date: 2026-05-18
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID


revision: str = "f9a0b1c2d3e4"
down_revision: Union[str, Sequence[str], None] = "e8f9a0b1c2d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Truncate existing chat history. ---
    # The workspace_id of past rows is not recoverable. Rather than
    # ship a permanent "legacy NULL bucket" query branch, drop the
    # rows. Pre-launch dev data only; documented at the head of this
    # file. TRUNCATE ... CASCADE follows chat → message → runs.
    op.execute("TRUNCATE TABLE chat CASCADE")

    # --- Add workspace_id NOT NULL FK. ---
    # No transient default needed: the table is empty after the
    # truncate above. NOT NULL is enforced from the start so the
    # agent-platform create path must persist it (X-CHAT-WS-1.3).
    op.add_column(
        "chat",
        sa.Column(
            "workspace_id",
            UUID(as_uuid=False),
            nullable=False,
        ),
    )
    op.create_foreign_key(
        "fk_chat_workspace_id",
        "chat",
        "workspace",
        ["workspace_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # --- Replace the old per-user index with the workspace-scoped one. ---
    op.drop_index("ix_chat_created_by", table_name="chat")
    op.create_index(
        "ix_chat_workspace_created_by_updated_at",
        "chat",
        ["workspace_id", "created_by", sa.text("updated_at DESC")],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    # Reverse the index swap, drop the FK + column. The truncated
    # history is not restored — the original workspace_id was never
    # recorded and there's no way to reconstruct it.
    op.drop_index(
        "ix_chat_workspace_created_by_updated_at", table_name="chat"
    )
    op.create_index(
        "ix_chat_created_by", "chat", ["tenant_id", "created_by"]
    )

    op.drop_constraint("fk_chat_workspace_id", "chat", type_="foreignkey")
    op.drop_column("chat", "workspace_id")
