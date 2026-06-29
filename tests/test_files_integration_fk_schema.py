"""[NEU-1816] UC-ES-DB-1.B + .E — files repoints onto integration, legacy
connector tables removed.

Collapses the legacy connector schema onto the canonical ``integration``
table. The ``datasources`` table (and its sister tables
``connections``, ``connector_types``, ``credentials``) was a parallel
model that pre-dated ``integration``; it had no rich auth / identity /
capability concepts and was only kept because ``files.datasource_id``
needed something to point at. With UC-ES-DB-1.A relaxing
``integration`` to accept local upload sources (``auth_kind='none'``),
the canonical table can express everything the legacy tables did. The
legacy tables die here, ``files`` re-points to ``integration``, and the
ES upload flow joins the same canonical model that Jira and DA already
use.

Pre-production (per [[project_pre_production_no_real_users]]) — no
backfill, no dual-write. ``files`` is TRUNCATEd in the migration; the
single test user re-uploads.

Contract points pinned by this test:

  1. ``files`` no longer has a ``datasource_id`` column.
  2. ``files`` has ``integration_id`` UUID NOT NULL FK to
     ``integration.id`` with ON DELETE CASCADE.
  3. None of ``datasources``, ``connections``, ``connector_types``,
     ``credentials`` exist.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa


_LEGACY_CONNECTOR_TABLES = (
    "datasources",
    "connections",
    "connector_types",
    "credentials",
)


async def _columns(test_engine, table_name: str) -> dict:
    async with test_engine.connect() as conn:
        return await conn.run_sync(
            lambda sync_conn: {
                c["name"]: c
                for c in sa.inspect(sync_conn).get_columns(table_name)
            }
        )


async def _foreign_keys(test_engine, table_name: str) -> list[dict]:
    async with test_engine.connect() as conn:
        return await conn.run_sync(
            lambda sync_conn: sa.inspect(sync_conn).get_foreign_keys(table_name)
        )


async def _table_exists(test_engine, table_name: str) -> bool:
    async with test_engine.connect() as conn:
        return await conn.run_sync(
            lambda sync_conn: sa.inspect(sync_conn).has_table(table_name)
        )


@pytest.mark.asyncio
async def test_files_has_integration_id_not_datasource_id(test_engine):
    cols = await _columns(test_engine, "files")
    assert "datasource_id" not in cols, (
        "files.datasource_id must be dropped — UC-ES-DB-1.B repoints "
        "files onto the canonical integration table."
    )
    assert "integration_id" in cols, (
        "files.integration_id must be present — UC-ES-DB-1.B adds the "
        "new FK after dropping datasource_id."
    )
    assert cols["integration_id"]["nullable"] is False, (
        "files.integration_id must be NOT NULL — every file belongs to "
        "an integration (member upload, OAuth source, etc.)."
    )


@pytest.mark.asyncio
async def test_files_integration_fk_targets_integration_with_cascade(test_engine):
    fks = await _foreign_keys(test_engine, "files")
    matching = [
        fk for fk in fks
        if "integration_id" in fk["constrained_columns"]
    ]
    assert matching, "files.integration_id has no foreign key constraint"
    fk = matching[0]
    assert fk["referred_table"] == "integration", (
        f"files.integration_id must reference integration.id; got {fk['referred_table']}"
    )
    assert "id" in fk["referred_columns"], (
        f"files.integration_id must reference integration.id; got column {fk['referred_columns']}"
    )
    on_delete = (fk.get("options") or {}).get("ondelete", "").upper()
    assert on_delete == "CASCADE", (
        "files.integration_id FK must be ON DELETE CASCADE — deleting "
        "an integration must cascade-delete its files. "
        f"Got ondelete={on_delete!r}."
    )


@pytest.mark.parametrize("table", _LEGACY_CONNECTOR_TABLES)
@pytest.mark.asyncio
async def test_legacy_connector_table_is_dropped(test_engine, table):
    assert not await _table_exists(test_engine, table), (
        f"Legacy connector table {table!r} still exists. UC-ES-DB-1 "
        "collapses datasources/connections/connector_types/credentials "
        "onto the canonical integration table — they must be dropped. "
        "If this test fails after the migration ran, check that the "
        "raw Table() defs are also removed from tables.py "
        "(Base.metadata.create_all would otherwise resurrect them)."
    )
