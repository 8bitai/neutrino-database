"""NC-151 Slice B — share_link (polymorphic share subsystem).

One sharing subsystem keyed by (resource_type, resource_id) — chat_artifact
today, dashboards/others later. Improves on DA's dashboard_link_token with a
`visibility` axis (public vs workspace-members-with-link), a curator `label`,
and last_accessed_at; keeps the SHA-256 token_hash / token_short / soft-delete /
CHECK-constraint hardening.

Two enums:
  * share_link_resource_type  chat_artifact
  * share_link_visibility     public | workspace

Pre-production: no rows to backfill.

Revision ID: d4b7e1c8a5f2
Revises: c2f5a8b1d3e6
Create Date: 2026-07-01
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ENUM, UUID


revision: str = "d4b7e1c8a5f2"
down_revision: Union[str, Sequence[str], None] = "c2f5a8b1d3e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


resource_type_enum = ENUM("chat_artifact", name="share_link_resource_type", create_type=False)
visibility_enum = ENUM("public", "workspace", name="share_link_visibility", create_type=False)


def upgrade() -> None:
    resource_type_enum.create(op.get_bind(), checkfirst=False)
    visibility_enum.create(op.get_bind(), checkfirst=False)

    op.create_table(
        "share_link",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=False), sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
        sa.Column("workspace_id", UUID(as_uuid=False), sa.ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False),
        sa.Column("resource_type", resource_type_enum, nullable=False),
        # Polymorphic — NOT a FK (points at different tables by resource_type).
        sa.Column("resource_id", UUID(as_uuid=False), nullable=False),
        sa.Column("visibility", visibility_enum, nullable=False, server_default=sa.text("'workspace'")),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("token_short", sa.String(length=12), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=True),
        sa.Column("created_by", UUID(as_uuid=False), sa.ForeignKey("user.id", ondelete="SET NULL"), nullable=True),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("revoked_by", UUID(as_uuid=False), sa.ForeignKey("user.id", ondelete="SET NULL"), nullable=True),
        sa.Column("accessed_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_accessed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("expires_at IS NULL OR expires_at > created_at", name="ck_share_link_expiry_after_creation"),
        sa.CheckConstraint("revoked_at IS NULL OR revoked_at >= created_at", name="ck_share_link_revoke_after_creation"),
    )

    op.create_index("ix_share_link_token_hash", "share_link", ["token_hash"], unique=True)
    op.create_index(
        "ix_share_link_resource_active",
        "share_link",
        ["resource_type", "resource_id"],
        postgresql_where=sa.text("revoked_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_share_link_resource_active", table_name="share_link")
    op.drop_index("ix_share_link_token_hash", table_name="share_link")
    op.drop_table("share_link")
    sa.Enum(name="share_link_visibility").drop(op.get_bind(), checkfirst=False)
    sa.Enum(name="share_link_resource_type").drop(op.get_bind(), checkfirst=False)
