"""[NEU-1816] UC-DELETE-VERTICALS — drop AIOps + Underwriting tables.

All three "verticals" (AIOps, Underwriting, Phonos) are removed from the
Neutrino platform — canon is the three pillars (Enterprise Search, Data
Analytics, Workflow Execution). This migration drops the 12 vertical-owned
tables from the canonical schema.

Pre-production context (per [[project_pre_production_no_real_users]]): no
real users, no backfill obligation. We drop and never restore. Source
alembic files that originally CREATEd these tables are left in
``versions/`` as historical record; this revision sits on top and removes
them from the live schema.

Tables dropped:

  * AIOps      — ai_ops_remedies, ai_ops_workflows, ai_ops_sops,
                 ai_ops_approvals, ai_ops_workflow_definitions
  * Logs       — log_connectors, log_field_mappings, ingested_logs
                 (AIOps log ingestion — ``ingested_logs`` was defined in
                 tables.py metadata but never had its own alembic CREATE;
                 dropped here for parity since ``create_all`` had been
                 materialising it on test runs)
  * Underwriting — underwriting_sessions, underwriting_session_documents,
                   underwriting_conversation_history,
                   underwriting_pipeline_results, underwriting_rules

Phonos had no DB tables — its surface was FE-only (call-recording widget +
agent picker branch). Cleanup happens in slice C.

Indices and FKs are removed implicitly via ``DROP TABLE ... CASCADE``. We
pass ``cascade=True`` rather than enumerating each index because the
intent is "the entire table and everything that depends on it must go" —
listing indices individually would risk drift if a migration in the chain
ever added an unanticipated one.

Revision ID: e1f2a3b4c5d6
Revises: d9e0f1a2b3c4
Create Date: 2026-05-31
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "e1f2a3b4c5d6"
down_revision: Union[str, Sequence[str]] = "d9e0f1a2b3c4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Order matters only for clarity (FKs are handled by CASCADE): child-ish
# tables first, parent-ish tables last.
_DROP_ORDER: tuple[str, ...] = (
    # AIOps
    "ai_ops_approvals",
    "ai_ops_workflows",
    "ai_ops_workflow_definitions",
    "ai_ops_sops",
    "ai_ops_remedies",
    # AIOps log ingestion
    "ingested_logs",
    "log_field_mappings",
    "log_connectors",
    # Underwriting
    "underwriting_session_documents",
    "underwriting_conversation_history",
    "underwriting_pipeline_results",
    "underwriting_rules",
    "underwriting_sessions",
)


def upgrade() -> None:
    for table in _DROP_ORDER:
        op.execute(f'DROP TABLE IF EXISTS "{table}" CASCADE')


def downgrade() -> None:
    raise NotImplementedError(
        "UC-DELETE-VERTICALS — vertical tables are intentionally not "
        "restorable. The canonical platform is three pillars only "
        "(Enterprise Search, Data Analytics, Workflow Execution). If you "
        "genuinely need an AIOps / Underwriting table back, restore the "
        "original CREATE migration files from git history (see e.g. "
        "134971f8d2a6_add_log_connectors_and_log_field_mappings.py)."
    )
