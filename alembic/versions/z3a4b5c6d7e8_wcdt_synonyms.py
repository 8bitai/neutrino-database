"""Add synonyms column to workspace_curation_da_table (DA-P1k.1).

Per-workspace alt-names for tables. Mirrors the existing
``workspace_curation_da_column.synonyms`` shape (JSONB list of strings).
Used by the workspace source detail page so admins can write "Customers"
as an alias for raw ``users`` — fed downstream to AI enrichment + the
chat-side classifier.

NULL = no synonyms set yet. Empty list semantically same as NULL but the
column allows both since clients have round-tripped lists before.

Revision ID: z3a4b5c6d7e8
Revises: y2z3a4b5c6d7
Create Date: 2026-05-12
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "z3a4b5c6d7e8"
down_revision: Union[str, Sequence[str], None] = "y2z3a4b5c6d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "workspace_curation_da_table",
        sa.Column("synonyms", JSONB, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("workspace_curation_da_table", "synonyms")
