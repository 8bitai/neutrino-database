"""widen files.file_type from varchar(20) to varchar(255) for MIME types

The ES-ingestion ``upload-init`` endpoint stores the client-provided MIME
content-type directly in ``files.file_type`` (controller does
``file_type=body.mime_type``). ``varchar(20)`` only fit short types such as
``application/pdf`` (15 chars); Office formats overflow, e.g. the .docx MIME
``application/vnd.openxmlformats-officedocument.wordprocessingml.document``
is 72 chars. That raised::

    asyncpg.exceptions.StringDataRightTruncationError:
    value too long for type character varying(20)

and turned every docx/xlsx/pptx upload into a 500. Widen to varchar(255),
which comfortably holds any registered MIME type.

Pre-production: no rows to backfill; widening cannot truncate existing data.

Revision ID: 52e581f60dfa
Revises: d7e8f9a0b1c2
Create Date: 2026-06-30
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "52e581f60dfa"
down_revision: Union[str, Sequence[str], None] = "d7e8f9a0b1c2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "files",
        "file_type",
        existing_type=sa.String(length=20),
        type_=sa.String(length=255),
        existing_nullable=True,
    )


def downgrade() -> None:
    # NOTE: narrowing back to 20 will fail if any stored MIME value exceeds
    # 20 chars (it will, for Office formats). Kept for symmetry only.
    op.alter_column(
        "files",
        "file_type",
        existing_type=sa.String(length=255),
        type_=sa.String(length=20),
        existing_nullable=True,
    )
