"""NC-137 — chat_attachment (ephemeral Unified Chat file uploads).

Claude-style upload-and-analyse for Unified Chat: a user attaches a
CSV/Excel, PDF, or image to a conversation and the agent analyses it in
the same turn. These attachments are a DIFFERENT lifecycle from
Enterprise Search ingestion (permanent, indexed, ACL'd via ``files``) and
from the DA Excel-dataset path (Excel -> Postgres queryable schema):
ephemeral, conversation-scoped, TTL'd, and never indexed. The distinct
status state machine (``uploaded -> processing -> ready``/``failed``),
TTL/GC sweep, and delete-with-chat cascade are why this is its own table
rather than a JSONB column on ``message``.

Two enums:
  * ``chat_attachment_kind``   tabular | document | image  (lane dispatch)
  * ``chat_attachment_status`` uploaded | processing | ready | failed

Pre-production: no rows to backfill.

Revision ID: d7e8f9a0b1c2
Revises: b3d4f5a6c7e8
Create Date: 2026-06-29
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ENUM, UUID


revision: str = "d7e8f9a0b1c2"
down_revision: Union[str, Sequence[str], None] = "b3d4f5a6c7e8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# One enum object per type, shared between explicit .create() and the column
# reference so SQLAlchemy doesn't auto-create on column bind.
kind_enum = ENUM(
    "tabular", "document", "image",
    name="chat_attachment_kind",
    create_type=False,
)
status_enum = ENUM(
    "uploaded", "processing", "ready", "failed",
    name="chat_attachment_status",
    create_type=False,
)


def upgrade() -> None:
    kind_enum.create(op.get_bind(), checkfirst=False)
    status_enum.create(op.get_bind(), checkfirst=False)

    op.create_table(
        "chat_attachment",
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
        # Nullable: upload can precede the chat row; linked on send. CASCADE
        # purges with the chat; NULL orphans are reaped by the TTL sweep.
        sa.Column(
            "chat_id",
            UUID(as_uuid=False),
            sa.ForeignKey("chat.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "message_id",
            UUID(as_uuid=False),
            sa.ForeignKey("message.id", ondelete="CASCADE"),
            nullable=True,
        ),
        # Always set at insert; SET NULL on user delete (mirrors chat.created_by).
        sa.Column(
            "uploaded_by",
            UUID(as_uuid=False),
            sa.ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("filename", sa.String(length=512), nullable=False),
        sa.Column("mime_type", sa.String(length=255), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("extracted_text_key", sa.Text(), nullable=True),
        sa.Column("kind", kind_enum, nullable=False),
        sa.Column(
            "status", status_enum, nullable=False, server_default=sa.text("'uploaded'")
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=True),
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
        "ix_chat_attachment_chat_id",
        "chat_attachment",
        ["chat_id"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "ix_chat_attachment_expires_at",
        "chat_attachment",
        ["expires_at"],
        postgresql_where=sa.text("deleted_at IS NULL AND expires_at IS NOT NULL"),
    )
    op.create_index(
        "ix_chat_attachment_uploaded_by",
        "chat_attachment",
        ["workspace_id", "uploaded_by"],
    )


def downgrade() -> None:
    op.drop_index("ix_chat_attachment_uploaded_by", table_name="chat_attachment")
    op.drop_index("ix_chat_attachment_expires_at", table_name="chat_attachment")
    op.drop_index("ix_chat_attachment_chat_id", table_name="chat_attachment")
    op.drop_table("chat_attachment")
    sa.Enum(name="chat_attachment_status").drop(op.get_bind(), checkfirst=False)
    sa.Enum(name="chat_attachment_kind").drop(op.get_bind(), checkfirst=False)
