"""[NEU-1816] UC-ES-DB-1.B + .E — repoint files.datasource_id onto
integration_id and drop the legacy datasources/connections/
connector_types/credentials tables.

Pre-production (per [[project_pre_production_no_real_users]]) so the
``files`` table is TRUNCATEd in this migration — the single test user
re-uploads. No backfill of ``files.datasource_id`` → ``integration_id``,
no dual-write window, no compatibility shim. Old rows die.

The legacy tables had FKs FROM:

  * ``files.datasource_id`` → ``datasources.id``      (dropped here)
  * ``connections.connector_type_id`` → ``connector_types.id``
  * ``credentials.connection_id`` → ``connections.id``

Drop order (child-first; CASCADE handles indices and any unanticipated
FK):

  credentials → connections → connector_types → datasources

For the files repoint:

  1. TRUNCATE files RESTART IDENTITY CASCADE — cascades to
     ingestion_jobs, parsing, chunk, and every other file_id-FK table
     so we don't leave orphan rows.
  2. DROP COLUMN files.datasource_id — the FK to datasources dies
     with the column.
  3. ADD COLUMN files.integration_id UUID NOT NULL REFERENCES
     integration(id) ON DELETE CASCADE — every file now belongs to
     an integration (member upload, OAuth source, etc.).

Revision ID: e3f4a5b6c7d8
Revises: e2f3a4b5c6d7
Create Date: 2026-05-31
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "e3f4a5b6c7d8"
down_revision: Union[str, Sequence[str]] = "e2f3a4b5c6d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) Wipe files (and everything that FKs into it). Pre-prod.
    op.execute("TRUNCATE TABLE files RESTART IDENTITY CASCADE")

    # 2) Drop the legacy FK column on files. The FK constraint to
    #    datasources is dropped implicitly.
    op.execute('ALTER TABLE files DROP COLUMN IF EXISTS datasource_id')

    # 3) Add the new canonical FK column on files.
    op.execute(
        'ALTER TABLE files '
        'ADD COLUMN integration_id UUID NOT NULL '
        'REFERENCES integration(id) ON DELETE CASCADE'
    )

    # 4) Drop the four legacy connector tables. Child-first so the
    #    operator can read the order; CASCADE handles any indices and
    #    leftover FKs from other unanticipated callers.
    for table in (
        "credentials",
        "connections",
        "connector_types",
        "datasources",
    ):
        op.execute(f'DROP TABLE IF EXISTS "{table}" CASCADE')


def downgrade() -> None:
    raise NotImplementedError(
        "UC-ES-DB-1.B+.E — the legacy connector schema is gone. "
        "Restoring would mean re-creating four tables, re-adding the "
        "datasource_id FK on files, and back-filling integration rows. "
        "Pre-production means there's no data to preserve; if you need "
        "the old schema back, restore the table CREATE migrations from "
        "git history and design a fresh migration."
    )
