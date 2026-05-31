"""[NEU-1816] UC-DELETE-VERTICALS.B — vertical tables must not exist.

AIOps, Underwriting, and Phonos were exploration verticals that no longer
belong on the Neutrino platform (canon is three pillars: Enterprise Search,
Data Analytics, Workflow Execution). This test pins the deletion of every
vertical-owned table from the canonical schema.

Pre-production: per [[project_pre_production_no_real_users]] we just drop
the tables in a new alembic migration — no backfill, no preservation,
no down() restore (down() raises NotImplementedError; restore from git
if ever needed).

Tables verified absent:

  * AIOps      — ai_ops_remedies, ai_ops_workflows, ai_ops_sops,
                 ai_ops_approvals, ai_ops_workflow_definitions
  * Logs       — log_connectors, log_field_mappings (AIOps log ingestion)
  * Underwriting — underwriting_sessions, underwriting_session_documents,
                   underwriting_conversation_history,
                   underwriting_pipeline_results, underwriting_rules
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa


_VERTICAL_TABLES = (
    # AIOps
    "ai_ops_remedies",
    "ai_ops_workflows",
    "ai_ops_sops",
    "ai_ops_approvals",
    "ai_ops_workflow_definitions",
    # AIOps log ingestion
    "log_connectors",
    "log_field_mappings",
    "ingested_logs",
    # Underwriting
    "underwriting_sessions",
    "underwriting_session_documents",
    "underwriting_conversation_history",
    "underwriting_pipeline_results",
    "underwriting_rules",
)


async def _table_exists(test_engine, table_name: str) -> bool:
    async with test_engine.connect() as conn:
        return await conn.run_sync(
            lambda sync_conn: sa.inspect(sync_conn).has_table(table_name)
        )


@pytest.mark.parametrize("table", _VERTICAL_TABLES)
@pytest.mark.asyncio
async def test_vertical_table_is_dropped(test_engine, table):
    assert not await _table_exists(test_engine, table), (
        f"Vertical table {table!r} still exists. UC-DELETE-VERTICALS adds "
        "an alembic migration that drops all 12 vertical tables. Run "
        "`alembic upgrade head` against the test DB after applying the "
        "migration to clear stale rows that pre-date the deletion."
    )
