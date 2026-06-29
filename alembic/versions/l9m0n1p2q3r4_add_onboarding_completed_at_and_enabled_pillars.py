"""Add tenant.onboarding_completed_at and workspace.enabled_pillars (multi-select pillars).

Two coordinated schema changes that land together so the FE post-auth
callback and the Persona B onboarding wizard can be built against
real signals (rather than the !workspace_id proxy and the conflated
single-value router_mode).

  1. ``tenant.onboarding_completed_at`` (TIMESTAMPTZ, NULL).
     First-class signal of "this tenant has finished initial
     onboarding." Stamped atomically by the upcoming
     ``POST /api/v1/onboarding/complete`` endpoint. Replaces the
     ``!workspace_id`` proxy used by ``decidePostLoginDestination``
     in the FE callback.

  2. ``pillar`` ENUM and ``workspace.enabled_pillars`` (pillar[],
     NOT NULL, DEFAULT ``'{}'``). Multi-select pillar enablement.
     Backfilled from the existing
     ``orchestrator_config.router_mode`` on the same workspace:

         router_mode      enabled_pillars
         ────────────────────────────────────────────────────────────
         AUTO          →  {ENTERPRISE_SEARCH, DATA_ANALYTICS, WORKFLOW_EXECUTION}
         SEARCH_ONLY   →  {ENTERPRISE_SEARCH}
         DA_ONLY       →  {DATA_ANALYTICS}
         ACTION_ONLY   →  {WORKFLOW_EXECUTION}

     Workspaces with no orchestrator_config row keep the column
     default (empty array) — the wizard or the workspace owner sets
     it later.

``orchestrator_config.router_mode`` is intentionally NOT removed by
this migration. It remains the source-of-truth for agent-platform
reads during a transition window; the gateway will write both
``enabled_pillars`` and ``router_mode``. A later cleanup migration
drops ``router_mode`` once downstream consumers read the new column.
See ``our-engineering-standards.md`` §10 (migration discipline) and
``user-stories/tenant-onboarding.md`` (locked decisions §1, §3).

Revision ID: l9m0n1p2q3r4
Revises: k8l9m0n1p2q3
Create Date: 2026-04-27 18:30:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "l9m0n1p2q3r4"
down_revision: Union[str, Sequence[str], None] = "k8l9m0n1p2q3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


PILLAR_ENUM_NAME = "pillar"
PILLAR_VALUES = ("ENTERPRISE_SEARCH", "DATA_ANALYTICS", "WORKFLOW_EXECUTION")


def upgrade() -> None:
    # 1. tenant.onboarding_completed_at
    op.add_column(
        "tenant",
        sa.Column(
            "onboarding_completed_at",
            sa.TIMESTAMP(timezone=True),
            nullable=True,
        ),
    )

    # 2. pillar enum + workspace.enabled_pillars (column added with
    #    server_default so existing rows pick up an empty array; we
    #    then backfill from orchestrator_config.router_mode where
    #    available).
    pillar_enum = postgresql.ENUM(
        *PILLAR_VALUES, name=PILLAR_ENUM_NAME, create_type=True
    )
    pillar_enum.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "workspace",
        sa.Column(
            "enabled_pillars",
            postgresql.ARRAY(
                postgresql.ENUM(
                    *PILLAR_VALUES,
                    name=PILLAR_ENUM_NAME,
                    create_type=False,
                )
            ),
            nullable=False,
            server_default=sa.text("'{}'::pillar[]"),
        ),
    )

    # Backfill from orchestrator_config.router_mode. The mapping
    # mirrors the agent-platform's interpretation of router_mode so
    # the new column reflects the same product behaviour.
    op.execute(
        """
        UPDATE workspace AS w
        SET enabled_pillars = CASE oc.router_mode
            WHEN 'AUTO' THEN
                ARRAY['ENTERPRISE_SEARCH', 'DATA_ANALYTICS', 'WORKFLOW_EXECUTION']::pillar[]
            WHEN 'SEARCH_ONLY' THEN
                ARRAY['ENTERPRISE_SEARCH']::pillar[]
            WHEN 'DA_ONLY' THEN
                ARRAY['DATA_ANALYTICS']::pillar[]
            WHEN 'ACTION_ONLY' THEN
                ARRAY['WORKFLOW_EXECUTION']::pillar[]
            ELSE w.enabled_pillars
        END
        FROM orchestrator_config AS oc
        WHERE oc.workspace_id = w.id;
        """
    )


def downgrade() -> None:
    op.drop_column("workspace", "enabled_pillars")
    pillar_enum = postgresql.ENUM(
        *PILLAR_VALUES, name=PILLAR_ENUM_NAME, create_type=False
    )
    pillar_enum.drop(op.get_bind(), checkfirst=True)
    op.drop_column("tenant", "onboarding_completed_at")
