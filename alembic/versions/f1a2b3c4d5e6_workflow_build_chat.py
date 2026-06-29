"""WF-AGENT — persist the "Build with Neutrino" workflow build chat.

The workflow build agent was fully ephemeral: its conversation lived only
in the browser, so a reload flushed it and the user could not resume where
they left off. This mirrors the Data Analytics dashboard-build pattern —
the conversation is a ``chat`` (kind=``workflow_build``) of ``message``
rows — so the build chat persists per workflow and replays on open.

Two changes:
  * ``chat_kind`` gains ``workflow_build``.
  * ``chat`` gains a nullable ``workflow_id`` FK (CASCADE) — the
    back-pointer to the workflow being built, mirroring ``dashboard_id``.

Pre-production: no existing workflow build chats to backfill.

Revision ID: f1a2b3c4d5e6
Revises: d1e2f3a4b5c6
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "f1a2b3c4d5e6"
down_revision: str | None = "d1e2f3a4b5c6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Postgres requires ADD VALUE outside the surrounding transaction before
    # the value can be referenced — same pattern as
    # ``0f8c72b60508_add_oauth2_app_only_auth_kind``.
    op.execute("ALTER TYPE chat_kind ADD VALUE IF NOT EXISTS 'workflow_build'")
    op.execute("COMMIT")

    op.add_column(
        "chat",
        sa.Column("workflow_id", sa.dialects.postgresql.UUID(as_uuid=False), nullable=True),
    )
    op.create_foreign_key(
        "fk_chat_workflow_id",
        "chat",
        "workflow",
        ["workflow_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_chat_workflow_id",
        "chat",
        ["workflow_id"],
        postgresql_where=sa.text("workflow_id IS NOT NULL AND deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_chat_workflow_id", table_name="chat")
    op.drop_constraint("fk_chat_workflow_id", "chat", type_="foreignkey")
    op.drop_column("chat", "workflow_id")
    # Postgres has no DROP VALUE for enums; the unused label is left in place
    # (pre-prod, no rows reference it).
