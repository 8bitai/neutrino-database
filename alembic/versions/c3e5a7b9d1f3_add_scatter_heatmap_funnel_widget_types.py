"""add 'scatter' / 'heatmap' / 'funnel' values to dashboard_widget_type enum

Expands the unified chart catalog (chart-stack convergence): scatter
(relationship between two measures), heatmap (measure across two
categorical dimensions, sequential ramp), funnel (staged/conversion
values). Each maps 1:1 to a shared ECharts chart body on the FE that
both the dashboard canvas and DA chat render.

Revision ID: c3e5a7b9d1f3
Revises: b2d4f6a8c0e2
Create Date: 2026-07-30
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "c3e5a7b9d1f3"
down_revision: Union[str, Sequence[str], None] = "b2d4f6a8c0e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ``ALTER TYPE ... ADD VALUE`` cannot run inside a transaction block, so
    # escape alembic's per-migration transaction for these statements.
    with op.get_context().autocommit_block():
        op.execute(
            "ALTER TYPE dashboard_widget_type "
            "ADD VALUE IF NOT EXISTS 'scatter' AFTER 'sankey'"
        )
        op.execute(
            "ALTER TYPE dashboard_widget_type "
            "ADD VALUE IF NOT EXISTS 'heatmap' AFTER 'scatter'"
        )
        op.execute(
            "ALTER TYPE dashboard_widget_type "
            "ADD VALUE IF NOT EXISTS 'funnel' AFTER 'heatmap'"
        )


def downgrade() -> None:
    # Postgres has no ``DROP VALUE`` for enums; removing a value requires
    # rebuilding the type. The extra values are harmless if unused, so this
    # is a no-op (kept for migration symmetry).
    pass
