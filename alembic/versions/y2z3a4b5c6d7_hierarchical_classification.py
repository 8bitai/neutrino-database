"""Hierarchical PII / restricted classification (NEU-1811 DA-P1i.3).

Compliance classification needs to apply at every level of the catalog,
not just columns. A whole table (``hr.salaries``) or schema (``hr``) can
be restricted as a unit; cascading writes to every column would lose
column-level granularity and break with newly-discovered columns after
re-sync. Mature catalogs (Atlan, Collibra, Snowflake, dbt) use the
"effective classification at read time" pattern: each level stores its
own flag; a column is effectively classified if any level in its
parentage is.

This migration adds ``is_pii`` and ``is_restricted`` to
``da_catalog_schema`` and ``da_catalog_table``. The column-level flags
already exist (DA-P1g). Defaults are FALSE — existing rows stay
unclassified until a Tenant Admin tags them.

Revision ID: y2z3a4b5c6d7
Revises: x1y2z3a4b5c6
Create Date: 2026-05-11 23:30:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "y2z3a4b5c6d7"
down_revision: Union[str, Sequence[str], None] = "x1y2z3a4b5c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for table in ("da_catalog_schema", "da_catalog_table"):
        op.add_column(
            table,
            sa.Column(
                "is_pii",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
        )
        op.add_column(
            table,
            sa.Column(
                "is_restricted",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
        )


def downgrade() -> None:
    for table in ("da_catalog_schema", "da_catalog_table"):
        op.drop_column(table, "is_restricted")
        op.drop_column(table, "is_pii")
