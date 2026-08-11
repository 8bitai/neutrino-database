"""dashboard_build_run + dashboard_proposal_state

Two tables behind the dashboard build-chat reliability work:

  * ``dashboard_build_run`` — the build turn becomes a background job with an
    id, so a dropped connection / refresh / rolling deploy no longer loses a
    turn the agent already did the work for. Reuses the existing ``run_status``
    enum (same state machine as the unified-chat ``runs`` table).
  * ``dashboard_proposal_state`` — records applied / removed / dismissed per
    proposal. Widget deletes are hard deletes, so without this a deleted
    widget's proposal card is indistinguishable from a never-applied one and
    the chat re-offers "Apply".

Revision ID: f8a1c3d5e7b9
Revises: d4f6b8c0e2a4
Create Date: 2026-08-11
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "f8a1c3d5e7b9"
down_revision: Union[str, Sequence[str], None] = "d4f6b8c0e2a4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# The run-status type already exists (created with ``runs``); reference it
# without attempting a second CREATE TYPE.
_RUN_STATUS = postgresql.ENUM(
    "pending",
    "running",
    "waiting_input",
    "completed",
    "failed",
    "cancelled",
    name="run_status",
    create_type=False,
)

# Deliberately not named ``dashboard_proposal_state``: Postgres puts types and
# tables in the same namespace, so the type would collide with the table.
_PROPOSAL_STATE = postgresql.ENUM(
    "applied",
    "removed",
    "dismissed",
    name="dashboard_proposal_state_kind",
    create_type=False,
)


def upgrade() -> None:
    op.create_table(
        "dashboard_build_run",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("tenant.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("workspace.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "dashboard_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("dashboard.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "build_chat_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("chat.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "status",
            _RUN_STATUS,
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("user_message", sa.Text(), nullable=False),
        sa.Column("result_envelope", postgresql.JSONB(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
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
    )
    op.create_index(
        "ix_dashboard_build_run_dashboard_created",
        "dashboard_build_run",
        ["dashboard_id", "created_at"],
    )

    # Owned by this migration (unlike run_status, which predates it).
    _PROPOSAL_STATE.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "dashboard_proposal_state",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "dashboard_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("dashboard.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "message_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("message.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("proposal_index", sa.Integer(), nullable=False),
        sa.Column("state", _PROPOSAL_STATE, nullable=False),
        sa.Column(
            "widget_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("dashboard_widget.id", ondelete="SET NULL"),
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
        sa.UniqueConstraint(
            "message_id",
            "proposal_index",
            name="ux_dashboard_proposal_state_message_index",
        ),
    )
    op.create_index(
        "ix_dashboard_proposal_state_dashboard",
        "dashboard_proposal_state",
        ["dashboard_id"],
    )
    op.create_index(
        "ix_dashboard_proposal_state_widget",
        "dashboard_proposal_state",
        ["widget_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_dashboard_proposal_state_widget",
        table_name="dashboard_proposal_state",
    )
    op.drop_index(
        "ix_dashboard_proposal_state_dashboard",
        table_name="dashboard_proposal_state",
    )
    op.drop_table("dashboard_proposal_state")
    _PROPOSAL_STATE.drop(op.get_bind(), checkfirst=True)

    op.drop_index(
        "ix_dashboard_build_run_dashboard_created",
        table_name="dashboard_build_run",
    )
    op.drop_table("dashboard_build_run")
    # run_status is shared with ``runs`` — never dropped here.
