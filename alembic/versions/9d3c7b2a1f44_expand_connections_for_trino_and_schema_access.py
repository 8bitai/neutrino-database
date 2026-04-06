"""expand connections for multi-connector naming

Revision ID: 9d3c7b2a1f44
Revises: h1i2j3k4l5m6
Create Date: 2026-03-26
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9d3c7b2a1f44"
down_revision: Union[str, Sequence[str], None] = "h1i2j3k4l5m6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "connections",
        sa.Column("connection_name", sa.String(length=255), nullable=False, server_default="default"),
    )

    op.drop_constraint("ux_connection_workspace_connector_type", "connections", type_="unique")
    op.create_index(
        "ux_connection_tenant_workspace_type_name_active",
        "connections",
        ["tenant_id", "workspace_id", "connector_type_id", "connection_name"],
        unique=True,
        postgresql_where=sa.text("status != 'revoked'"),
    )


def downgrade() -> None:
    op.drop_index("ux_connection_tenant_workspace_type_name_active", table_name="connections")
    op.create_unique_constraint(
        "ux_connection_workspace_connector_type",
        "connections",
        ["workspace_id", "connector_type_id"],
    )

    op.drop_column("connections", "connection_name")
