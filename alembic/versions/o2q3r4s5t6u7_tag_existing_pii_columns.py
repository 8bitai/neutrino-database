"""Tag existing PII columns with pii:* COMMENT (NEU-1804 — PII foundation).

Backfills the PII tagging convention onto the columns we already had
when the audit log foundation landed. Going forward, every new column
that holds personally-identifiable information must carry
``COMMENT ON COLUMN ... IS 'pii:<category>'`` at creation time per
``our-engineering-standards.md`` § 13.

The future C6 anonymization runner reads ``pg_description`` to discover
which columns to anonymize when a user exercises GDPR Article 17 erasure.
Untagged PII = a hidden compliance gap; this migration closes the v1 gap.

Tagged columns:

  user.email                              pii:email
  user.display_name                       pii:name
  user.username                           pii:name
  workspace_invitation.email              pii:email
  workspace_invitation.personal_message   pii:freetext

The audit_log columns (ip_address, user_agent) were tagged in the
prior migration that created the table.

See ``user-stories/user-lifecycle.md`` § "PII inventory" for the
catalogue and the per-tag anonymization replacement values.

Revision ID: o2q3r4s5t6u7
Revises: n1p2q3r4s5t6
Create Date: 2026-04-29 13:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "o2q3r4s5t6u7"
down_revision: Union[str, Sequence[str], None] = "n1p2q3r4s5t6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (table, column, tag) — keep in lock-step with tests/test_pii_tagging.py
_PII_TAGS: list[tuple[str, str, str]] = [
    ('"user"', "email", "pii:email"),
    ('"user"', "display_name", "pii:name"),
    ('"user"', "username", "pii:name"),
    ("workspace_invitation", "email", "pii:email"),
    ("workspace_invitation", "personal_message", "pii:freetext"),
]


def upgrade() -> None:
    for table, column, tag in _PII_TAGS:
        op.execute(f"COMMENT ON COLUMN {table}.{column} IS '{tag}'")


def downgrade() -> None:
    for table, column, _tag in _PII_TAGS:
        op.execute(f"COMMENT ON COLUMN {table}.{column} IS NULL")
