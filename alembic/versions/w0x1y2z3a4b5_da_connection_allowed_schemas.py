"""Add allowed_schemas to da_connection (NEU-1811 DA-P1f).

Tenant-level schema allowlist for warehouse connections. Tenant Admin
optionally restricts which schemas the connection exposes to workspaces.

  NULL          → unrestricted (no allowlist); workspace admins see
                  every schema the warehouse exposes.
  list[str]     → whitelist; only these schemas are visible / queryable.

Stored as JSONB so the column is naturally a list of names. Defaults
to NULL so existing rows backfill cleanly with the unrestricted
behaviour they had before this slice.

Enforced at the connector-service layer:
  * adapter.list_schemas() returns the intersection of the warehouse's
    actual schemas and the allowlist
  * list_tables / list_columns / execute_query reject calls against
    schemas not on the allowlist

Migration is additive + backward-compatible: any existing connection
keeps its previous behaviour until an admin chooses to restrict.

Revision ID: w0x1y2z3a4b5
Revises: v9w0x1y2z3a4
Create Date: 2026-05-11 22:30:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "w0x1y2z3a4b5"
down_revision: Union[str, Sequence[str], None] = "v9w0x1y2z3a4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "da_connection",
        sa.Column(
            "allowed_schemas",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("da_connection", "allowed_schemas")
