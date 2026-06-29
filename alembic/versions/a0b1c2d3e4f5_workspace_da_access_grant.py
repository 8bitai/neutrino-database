"""Add workspace_da_access_grant — per-member DA ACL projection (X-DA-ACL-1).

Adds the projection table that stores explicit allow/deny grants on
DA catalog resources (schemas / tables / columns) for each workspace
member. The absence of a row at a given level means "inherit from
parent" — resolution walks the resource tree from leaf upward,
applying the closest explicit row.

Two enums:

  * ``da_access_resource_type``  schema | table | column
  * ``da_access_effect``         allow | deny

One table with two composite indexes for the UI read paths:

  * (workspace_id, user_id)               — member-summary view
  * (workspace_id, resource_type, resource_id) — resource Access drawer

Unique constraint (workspace_id, user_id, resource_type, resource_id)
keeps the "current state" of any matrix cell unambiguous.

FK CASCADE on workspace_id and user_id so leaving a workspace or
losing a user account purges their grant projection rows.

Resolution semantics (encoded in the service, not the schema):

  * Closest level with an explicit row wins.
  * At the same level deny beats allow (UNIQUE makes that
    impossible at the column row itself; rule kicks in across levels).
  * Tenant Owner / Tenant Admin / Workspace Admin bypass entirely.
  * M10 PII / Restricted catalog flags hard-block above all of this.

Revision ID: a0b1c2d3e4f5
Revises: f9a0b1c2d3e4
Create Date: 2026-05-19
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ENUM, UUID


revision: str = "a0b1c2d3e4f5"
down_revision: Union[str, Sequence[str], None] = "f9a0b1c2d3e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# One enum object per type, shared between explicit .create() and the
# column reference so SQLAlchemy doesn't try to auto-create on column
# bind. ``create_type=False`` is what suppresses the implicit create.
resource_type_enum = ENUM(
    "schema",
    "table",
    "column",
    name="da_access_resource_type",
    create_type=False,
)
access_effect_enum = ENUM(
    "allow",
    "deny",
    name="da_access_effect",
    create_type=False,
)


def upgrade() -> None:
    resource_type_enum.create(op.get_bind(), checkfirst=False)
    access_effect_enum.create(op.get_bind(), checkfirst=False)

    op.create_table(
        "workspace_da_access_grant",
        sa.Column(
            "id",
            UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "workspace_id",
            UUID(as_uuid=False),
            sa.ForeignKey("workspace.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            UUID(as_uuid=False),
            sa.ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("resource_type", resource_type_enum, nullable=False),
        sa.Column("resource_id", UUID(as_uuid=False), nullable=False),
        sa.Column("effect", access_effect_enum, nullable=False),
        sa.Column(
            "created_by",
            UUID(as_uuid=False),
            sa.ForeignKey("user.id", ondelete="SET NULL"),
            nullable=False,
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
            onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "user_id",
            "resource_type",
            "resource_id",
            name="ux_workspace_da_access_grant_member_resource",
        ),
    )
    op.create_index(
        "ix_workspace_da_access_grant_workspace_user",
        "workspace_da_access_grant",
        ["workspace_id", "user_id"],
    )
    op.create_index(
        "ix_workspace_da_access_grant_workspace_resource",
        "workspace_da_access_grant",
        ["workspace_id", "resource_type", "resource_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_workspace_da_access_grant_workspace_resource",
        table_name="workspace_da_access_grant",
    )
    op.drop_index(
        "ix_workspace_da_access_grant_workspace_user",
        table_name="workspace_da_access_grant",
    )
    op.drop_table("workspace_da_access_grant")
    sa.Enum(name="da_access_effect").drop(op.get_bind(), checkfirst=False)
    sa.Enum(name="da_access_resource_type").drop(op.get_bind(), checkfirst=False)
