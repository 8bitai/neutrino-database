"""add 'sankey' value to dashboard_widget_type enum

Extends the v1 dashboard widget catalog with a Sankey diagram widget.
The widget renders flow/transition data (edge lists of source → target →
value) via the ECharts sankey series on the dashboard canvas; the build
agent emits it with ``viz_spec = {chart_type, source, target, value}``.

Revision ID: b2d4f6a8c0e2
Revises: a1c3e5b7d9f2
Create Date: 2026-07-29
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "b2d4f6a8c0e2"
down_revision: Union[str, Sequence[str], None] = "a1c3e5b7d9f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ``ALTER TYPE ... ADD VALUE`` cannot run inside a transaction block, so
    # escape alembic's per-migration transaction for this statement.
    with op.get_context().autocommit_block():
        op.execute(
            "ALTER TYPE dashboard_widget_type "
            "ADD VALUE IF NOT EXISTS 'sankey' AFTER 'donut_chart'"
        )


def downgrade() -> None:
    # Postgres has no ``DROP VALUE`` for enums; removing a value requires
    # rebuilding the type. The extra value is harmless if unused, so this is a
    # no-op (kept for migration symmetry).
    pass
