"""merge heads: 'converting' enum + chat_attachment.direction

Two migrations branched off ``52e581f60dfa`` and left the history with two
heads:

  - ``a7c9e2b4d6f8`` — chat_attachment.direction (NC-149, outbound report exports)
  - ``cf17a2b9d3e4`` — add 'converting' to file_processing_status (NC-112, MinerU
    office-doc -> PDF conversion stage)

With two heads, ``alembic upgrade head`` is ambiguous and refuses to run. This
merge unifies them into a single head so upgrade/downgrade round-trips cleanly
again. It is a pure DAG join — no schema change (empty upgrade/downgrade).

Revision ID: d2e4f6a8c0b1
Revises: a7c9e2b4d6f8, cf17a2b9d3e4
Create Date: 2026-07-01
"""

from __future__ import annotations

from typing import Sequence, Union


revision: str = "d2e4f6a8c0b1"
down_revision: Union[str, Sequence[str], None] = ("a7c9e2b4d6f8", "cf17a2b9d3e4")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
