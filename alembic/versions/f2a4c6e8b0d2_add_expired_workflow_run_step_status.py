"""add 'expired' value to workflow_run_step_status enum

A human-wait node (approval / form) previously waited forever: nothing bounded
how long a person had to answer, so an unanswered gate parked the run
indefinitely with no signal that nobody had looked at it. NC-257 gives every
wait a deadline that escalates through the configured approver tiers and, after
the last tier, resolves the wait to an explicit ``expired`` outcome — the run
stays alive (the Case stays open) and nothing downstream executes.

That outcome needs its own status on ``workflow_run_step``. The existing values
all misreport it:

  * ``succeeded`` — nobody decided. A green row would hide the fact that the
    gate went unanswered, which is precisely the dishonesty NC-257 removes.
  * ``failed``    — nothing malfunctioned. No activity errored and no retries
    were exhausted; a human simply did not respond. Counting these as failures
    corrupts failure metrics and alerting.
  * ``skipped``   — the node *was* reached and *did* run: it notified the
    approvers and waited. ``skipped`` means a branch was not taken.

The column binds the enum with ``values_callable``
(``tables.py`` ``workflow_run_step.status``), so the PG labels are the
lowercase values and the new label is ``'expired'``.

Deploy ordering: this migration must be applied BEFORE the neutrino-workflow-
service change that writes the new value, or those inserts fail.

Revision ID: f2a4c6e8b0d2
Revises: d4f6b8c0e2a4
Create Date: 2026-08-06
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "f2a4c6e8b0d2"
down_revision: Union[str, Sequence[str], None] = "d4f6b8c0e2a4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ``ALTER TYPE ... ADD VALUE`` cannot run inside a transaction block, so
    # escape alembic's per-migration transaction for this statement.
    with op.get_context().autocommit_block():
        op.execute(
            "ALTER TYPE workflow_run_step_status "
            "ADD VALUE IF NOT EXISTS 'expired' AFTER 'skipped'"
        )


def downgrade() -> None:
    # Postgres has no ``DROP VALUE`` for enums; removing a value requires
    # rebuilding the type. The extra value is harmless if unused, so this is a
    # no-op (kept for migration symmetry) — matching
    # cf17a2b9d3e4_add_converting_file_processing_status.
    pass
