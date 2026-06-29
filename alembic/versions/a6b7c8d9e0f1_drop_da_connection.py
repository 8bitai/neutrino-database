"""Drop the legacy da_connection table (DA-U6).

DA warehouse connections fully moved onto the unified `integration` table
across connector-service (DA-U3) and agent-platform (DA-U4); no application
code reads `da_connection` anymore and no FK references it (the catalog's
parent FK was repointed to `integration` in DA-U2). This drops the now-dead
table, completing the DA leg of the connector unification.

The `da_source_type` / `da_connection_status` Postgres enum types are left in
place — connector-service still uses the Python `DASourceTypeEnum` /
`DAConnectionStatusEnum` for its API DTO (the DA-facing status is derived from
`integration.metadata.capability_status`), and downgrade recreates the table
against them.

Revision ID: a6b7c8d9e0f1
Revises: f5a6b7c8d9e0
Create Date: 2026-05-24
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ENUM, JSONB, UUID

revision: str = "a6b7c8d9e0f1"
down_revision: Union[str, Sequence[str], None] = "f5a6b7c8d9e0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table("da_connection")


def downgrade() -> None:
    # Recreate the table against the still-present enum types (create_type=False).
    op.create_table(
        "da_connection",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "tenant_id",
            UUID(as_uuid=False),
            sa.ForeignKey("tenant.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "source_type",
            ENUM(name="da_source_type", create_type=False),
            nullable=False,
        ),
        sa.Column("connection_name", sa.String(255), nullable=False),
        sa.Column("credentials", JSONB, nullable=False, comment="pii:credentials"),
        sa.Column(
            "status",
            ENUM(name="da_connection_status", create_type=False),
            nullable=False,
            server_default=sa.text("'pending_auth'"),
        ),
        sa.Column("allowed_schemas", JSONB, nullable=True),
        sa.Column(
            "created_by",
            UUID(as_uuid=False),
            sa.ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ux_da_connection_tenant_source_name",
        "da_connection",
        ["tenant_id", "source_type", "connection_name"],
        unique=True,
    )
    op.create_index("ix_da_connection_tenant", "da_connection", ["tenant_id"])
