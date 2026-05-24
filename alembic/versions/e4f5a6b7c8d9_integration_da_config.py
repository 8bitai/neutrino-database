"""Add integration_da_config (DA-U1).

The DA capability's per-connection config sidecar for the unified `integration`
table — the first slice of moving Data Analytics warehouse connections off the
legacy `da_connection` table. Holds the DA-specific tenant schema allowlist
(was da_connection.allowed_schemas), 1:1 with the integration. Generic
integration fields (provider, status, credentials ref, capabilities) live on
`integration` itself. The data migration of existing da_connection rows lands
in DA-U2.

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
Create Date: 2026-05-24
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "e4f5a6b7c8d9"
down_revision: Union[str, Sequence[str], None] = "d3e4f5a6b7c8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "integration_da_config",
        sa.Column(
            "integration_id",
            UUID(as_uuid=False),
            sa.ForeignKey("integration.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        # NULL = unrestricted; list[str] = schema allowlist (same semantics as
        # the legacy da_connection.allowed_schemas this replaces).
        sa.Column("allowed_schemas", JSONB, nullable=True),
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


def downgrade() -> None:
    op.drop_table("integration_da_config")
