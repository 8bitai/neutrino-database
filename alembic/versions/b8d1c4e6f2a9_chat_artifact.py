"""NC-151 — chat_artifact (durable unified-agent artifacts).

A unified-agent turn produces *artifacts*: renderable, addressable outputs — a
governed structured chart/table/kpi, or a model-authored generative html/doc
page ("a full dashboard page and more"). Today a chart lives only in the message
JSON envelope (inherited from DA), so it has no durable, server-addressable
identity — nothing to open in its own view, version, or (Slice B) share by link.
This table gives it that identity.

Deliberately a UNIFIED-AGENT primitive, not a DA/ES concept: no pillar-specific
columns; ``kind`` + a JSONB ``content`` payload model every render family, so
DA's ECharts is just one ``chart`` producer, not a special case.

One enum:
  * ``chat_artifact_kind``  chart | table | kpi | html | doc  (render family)

ondelete posture (durable-snapshot intent):
  * chat_id      NOT NULL, CASCADE  — dies with its chat
  * message_id   nullable, SET NULL — outlives an edited/deleted origin turn
  * created_by   nullable, SET NULL — a departed author doesn't destroy artifacts
  * derived_from_artifact_id self-FK SET NULL — a fork survives its parent

Pre-production: no rows to backfill.

Revision ID: b8d1c4e6f2a9
Revises: a7c9e2b4d6f8
Create Date: 2026-07-01
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ENUM, JSONB, UUID


revision: str = "b8d1c4e6f2a9"
down_revision: Union[str, Sequence[str], None] = "a7c9e2b4d6f8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# One enum object, shared between explicit .create() and the column reference so
# SQLAlchemy doesn't auto-create on column bind.
kind_enum = ENUM(
    "chart", "table", "kpi", "html", "doc",
    name="chat_artifact_kind",
    create_type=False,
)


def upgrade() -> None:
    kind_enum.create(op.get_bind(), checkfirst=False)

    op.create_table(
        "chat_artifact",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "tenant_id",
            UUID(as_uuid=False),
            sa.ForeignKey("tenant.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "workspace_id",
            UUID(as_uuid=False),
            sa.ForeignKey("workspace.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # NOT NULL: the agent emits it mid-turn, so the chat already exists.
        sa.Column(
            "chat_id",
            UUID(as_uuid=False),
            sa.ForeignKey("chat.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # SET NULL, not CASCADE: a durable/shareable snapshot must outlive its
        # origin message (a Slice B link must not 404 on a trimmed turn).
        sa.Column(
            "message_id",
            UUID(as_uuid=False),
            sa.ForeignKey("message.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_by",
            UUID(as_uuid=False),
            sa.ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("kind", kind_enum, nullable=False),
        sa.Column("title", sa.String(length=512), nullable=True),
        # Whole render payload inline (structured spec+data, or {"html": ...}).
        sa.Column("content", JSONB(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        # Lineage for revisualize/fork; self-FK SET NULL so a fork survives.
        sa.Column(
            "derived_from_artifact_id",
            UUID(as_uuid=False),
            sa.ForeignKey("chat_artifact.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )

    op.create_index(
        "ix_chat_artifact_chat_id",
        "chat_artifact",
        ["chat_id"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "ix_chat_artifact_message_id",
        "chat_artifact",
        ["message_id"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_chat_artifact_message_id", table_name="chat_artifact")
    op.drop_index("ix_chat_artifact_chat_id", table_name="chat_artifact")
    op.drop_table("chat_artifact")
    sa.Enum(name="chat_artifact_kind").drop(op.get_bind(), checkfirst=False)
