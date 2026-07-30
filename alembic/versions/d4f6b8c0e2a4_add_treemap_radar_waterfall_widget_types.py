"""add 'treemap' / 'radar' / 'waterfall' values to dashboard_widget_type enum

Second catalog expansion of the unified chart stack: treemap
(proportional share when a pie gets crowded), radar (a few entities
compared across 3+ metrics), waterfall (signed contributions to a
running total). Each maps 1:1 to a shared ECharts chart body rendered
by both the dashboard canvas and DA chat.

Revision ID: d4f6b8c0e2a4
Revises: c3e5a7b9d1f3
Create Date: 2026-07-30
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "d4f6b8c0e2a4"
down_revision: Union[str, Sequence[str], None] = "c3e5a7b9d1f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ``ALTER TYPE ... ADD VALUE`` cannot run inside a transaction block, so
    # escape alembic's per-migration transaction for these statements.
    with op.get_context().autocommit_block():
        op.execute(
            "ALTER TYPE dashboard_widget_type "
            "ADD VALUE IF NOT EXISTS 'treemap' AFTER 'funnel'"
        )
        op.execute(
            "ALTER TYPE dashboard_widget_type "
            "ADD VALUE IF NOT EXISTS 'radar' AFTER 'treemap'"
        )
        op.execute(
            "ALTER TYPE dashboard_widget_type "
            "ADD VALUE IF NOT EXISTS 'waterfall' AFTER 'radar'"
        )


def downgrade() -> None:
    # Postgres has no ``DROP VALUE`` for enums; removing a value requires
    # rebuilding the type. The extra values are harmless if unused, so this
    # is a no-op (kept for migration symmetry).
    pass
