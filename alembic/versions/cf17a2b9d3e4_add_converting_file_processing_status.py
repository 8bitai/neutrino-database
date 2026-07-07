"""add 'converting' value to file_processing_status enum

Office documents (docx/doc/pptx/ppt/xlsx/xls/odt/ods/odp) cannot be parsed
directly by MinerU — it pages over a rendered PDF, and a flowing Word/Office
stream has no fixed page count until a layout engine renders it. The ingestion
pipeline (``DocumentLifecycleWorkflow``) now converts office docs to PDF in a new
stage that sits between ``fetched`` and ``parsing``; PDFs skip it entirely. This
migration teaches the ``file_processing_status`` PG enum the new ``converting``
value so ``documents__update_status`` can write it.

See ``22-docx-conversion-pipeline-integration.md`` for the full design.

Revision ID: cf17a2b9d3e4
Revises: 52e581f60dfa
Create Date: 2026-06-30
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "cf17a2b9d3e4"
down_revision: Union[str, Sequence[str], None] = "52e581f60dfa"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ``ALTER TYPE ... ADD VALUE`` cannot run inside a transaction block, so
    # escape alembic's per-migration transaction for this statement.
    with op.get_context().autocommit_block():
        op.execute(
            "ALTER TYPE file_processing_status "
            "ADD VALUE IF NOT EXISTS 'converting' AFTER 'fetched'"
        )


def downgrade() -> None:
    # Postgres has no ``DROP VALUE`` for enums; removing a value requires
    # rebuilding the type. The extra value is harmless if unused, so this is a
    # no-op (kept for migration symmetry).
    pass
