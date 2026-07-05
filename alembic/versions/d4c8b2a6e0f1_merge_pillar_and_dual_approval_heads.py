"""Merge the open migration heads into a single head.

The migration graph carried several unmerged heads, so ``alembic upgrade
head`` errored with "multiple heads present":

    f8a9b0c1d2e3  (add_dual_approval_columns)
    8a6d3f313f43  (added_workspace_tables)
    d4b7e1c8a5f2  (share_link) — tip of the chat_artifact / share_link
                   lineage that descends from
                   d2e4f6a8c0b1 (merge_converting_and_chat_attachment_
                   direction_heads)

None is an ancestor of the others — they are genuinely divergent
branches. This is a no-op merge migration: it introduces no schema
changes, it only reconciles the heads so a single linear head exists
for subsequent migrations (the ``chat.pillar`` columns) to chain off.
See our-engineering-standards.md §10 (migration discipline).

Revision ID: d4c8b2a6e0f1
Revises: f8a9b0c1d2e3, 8a6d3f313f43, d4b7e1c8a5f2
Create Date: 2026-07-02 00:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union


revision: str = "d4c8b2a6e0f1"
down_revision: Union[str, Sequence[str], None] = (
    "f8a9b0c1d2e3",
    "8a6d3f313f43",
    "d4b7e1c8a5f2",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
